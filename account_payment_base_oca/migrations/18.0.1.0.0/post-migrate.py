#  License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade, openupgrade_180
from psycopg2.extras import Json

logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.add_columns(
        env,
        [("account.payment.method.line", "old_payment_mode_id", "integer")],
    )
    _create_payment_mode_lines(env)
    _set_show_bank_account(env)
    _set_variable_journals(env)
    _create_fixed_lines_for_variable_modes(env)
    _set_payment_accounts(env)
    _set_refund_lines(env)
    _set_move_preferred_payment_method_line(env)
    _set_partner_payment_method_line(env)


def _create_payment_mode_lines(env):
    """Transform each payment mode into an account.payment.method.line.

    A method line already exists on the journal of a payment mode with a fixed
    link and the existing account.payment records point to it. So we REUSE it
    instead of creating a duplicate: the line takes the name and the options of
    the payment mode, keeping the link with the payments history. A new line is
    only created when there is no line left for the (journal, payment method)
    pair: a variable link (no journal on the line) or a second payment mode
    using the same journal and payment method as another one.

    ``payment_account_id`` is filled by ``_set_payment_accounts()``.
    """
    cr = env.cr
    cr.execute(
        """
        SELECT
            apm.id,
            apm.name,
            apm.company_id,
            apm.payment_method_id,
            apm.bank_account_link,
            apm.fixed_journal_id,
            COALESCE(apm.sequence, 10) AS sequence,
            apm.active,
            apm.note
        FROM account_payment_mode apm
        ORDER BY apm.id
        """
    )
    modes = cr.dictfetchall()
    claimed_line_ids = set()
    for mode in modes:
        line_id = _find_reusable_fixed_line(cr, mode, claimed_line_ids)
        if line_id:
            _update_method_line_from_mode(cr, line_id, mode)
        else:
            line_id = _create_method_line_from_mode(cr, mode)
        claimed_line_ids.add(line_id)


def _find_reusable_fixed_line(cr, mode, claimed_line_ids):
    """Return the id of the existing method line of the journal and payment
    method of a payment mode with a fixed link, if it exists and is not already
    used by another payment mode."""
    if mode["bank_account_link"] != "fixed" or not mode["fixed_journal_id"]:
        return False
    # Only the lines with a fixed link have a journal: the lines with a
    # variable link get journal_id = NULL (see _create_method_line_from_mode).
    query = """
        SELECT apml.id
        FROM account_payment_method_line apml
        WHERE apml.journal_id = %s
          AND apml.payment_method_id = %s
    """
    args = [mode["fixed_journal_id"], mode["payment_method_id"]]
    if claimed_line_ids:
        query += " AND apml.id NOT IN %s"
        args.append(tuple(claimed_line_ids))
    query += " ORDER BY apml.id LIMIT 1"
    cr.execute(query, args)
    row = cr.fetchone()
    return row[0] if row else False


def _update_method_line_from_mode(cr, line_id, mode):
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_payment_method_line
        SET name = %s,
            sequence = %s,
            bank_account_link = 'fixed',
            selectable = TRUE,
            active = %s,
            report_description = %s,
            old_payment_mode_id = %s
        WHERE id = %s
        """,
        (
            Json(mode["name"]),
            mode["sequence"],
            mode["active"],
            Json(mode["note"]) if mode["note"] else None,
            mode["id"],
            line_id,
        ),
    )


def _create_method_line_from_mode(cr, mode):
    if mode["bank_account_link"] == "fixed":
        journal_id = mode["fixed_journal_id"]
    else:
        journal_id = None
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO account_payment_method_line (
            name, sequence, payment_method_id, journal_id, bank_account_link,
            selectable, company_id, active, create_date, write_date,
            report_description, old_payment_mode_id
        )
        VALUES (
            %s, %s, %s, %s, %s, TRUE, %s, %s, NOW(), NOW(), %s, %s
        )
        RETURNING id
        """,
        (
            Json(mode["name"]),
            mode["sequence"],
            mode["payment_method_id"],
            journal_id,
            mode["bank_account_link"],
            mode["company_id"],
            mode["active"],
            Json(mode["note"]) if mode["note"] else None,
            mode["id"],
        ),
    )
    return cr.fetchone()[0]


def _set_show_bank_account(env):
    """Copy the options of the payment modes which come from
    account_payment_partner, merged into this module (the columns don't exist
    if only account_payment_mode was installed)."""
    cr = env.cr
    if not openupgrade.column_exists(cr, "account_payment_mode", "show_bank_account"):
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_payment_method_line apml
        SET show_bank_account = apm.show_bank_account,
            show_bank_account_chars = apm.show_bank_account_chars
        FROM account_payment_mode apm
        WHERE apm.id = apml.old_payment_mode_id
        """,
    )


def _set_variable_journals(env):
    """Fill the allowed bank journals of the method lines created from a
    payment mode with a variable link.
    """
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO account_payment_method_line_variable_journal_rel
            (method_line_id, journal_id)
        SELECT apml.id, rel.journal_id
        FROM account_payment_mode_variable_journal_rel rel
        JOIN account_payment_method_line apml
            ON apml.old_payment_mode_id = rel.payment_mode_id
        WHERE apml.bank_account_link = 'variable'
        """,
    )


def _create_fixed_lines_for_variable_modes(env):
    """Create a non-selectable fixed method line for each journal allowed on a
    payment mode with a variable link, when no line exists yet for this journal
    and this payment method.

    In v18 the account.payment must be linked to a method line with a journal
    (see ``_prepare_account_payment_vals()`` in account_payment_batch_oca): the
    method line with the variable link can not be used for that. Only the
    variable line is selectable on partners/invoices; the user still selects
    the journal on the payment order.
    """
    openupgrade.logged_query(
        env.cr,
        """
        WITH needed AS (
            SELECT DISTINCT rel.journal_id, apml.payment_method_id
            FROM account_payment_mode_variable_journal_rel rel
            JOIN account_payment_method_line apml
                ON apml.old_payment_mode_id = rel.payment_mode_id
            WHERE apml.bank_account_link = 'variable'
        ),
        missing AS (
            SELECT needed.journal_id, needed.payment_method_id, aj.company_id
            FROM needed
            JOIN account_journal aj ON aj.id = needed.journal_id
            WHERE NOT EXISTS (
                -- only the lines with a fixed link have a journal, so any
                -- line found here is already a valid carrier line
                SELECT 1
                FROM account_payment_method_line apml
                WHERE apml.journal_id = needed.journal_id
                  AND apml.payment_method_id = needed.payment_method_id
            )
        )
        INSERT INTO account_payment_method_line (
            name, sequence, payment_method_id, journal_id, bank_account_link,
            selectable, company_id, active, create_date, write_date,
            show_bank_account
        )
        SELECT
            apm.name, 10, missing.payment_method_id, missing.journal_id,
            'fixed', FALSE, missing.company_id, TRUE, NOW(), NOW(), 'no'
        FROM missing
        JOIN account_payment_method apm ON apm.id = missing.payment_method_id
        """,
    )


def _set_payment_accounts(env):
    """Set the outstanding account on the method lines created by this
    migration.

    In v17 the outstanding account was on the company
    (res_company.account_journal_payment_debit/credit_account_id): every
    payment on a bank/cash journal generated a journal entry. In v18 it is on
    the method line, and a method line without it is valid but means "no
    journal entry for this payment method" (the payment is created without a
    move, so it doesn't reconcile the invoice).

    Migrating the payment modes without the account would silently switch them
    to that behaviour, so we take the same value the core 'account' migration
    script used to fill the existing method lines: the old company accounts,
    chosen by payment type. Do not confuse them with the bank account of the
    journal (journal.default_account_id / bank_account_id).
    """
    cr = env.cr
    if not openupgrade.column_exists(
        cr, "res_company", "account_journal_payment_debit_account_id"
    ):
        logger.warning(
            "res_company.account_journal_payment_debit/credit_account_id are "
            "gone: the method lines created by this migration have no "
            "outstanding account, so the payments made with them will not "
            "generate any journal entry"
        )
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_payment_method_line apml
        SET payment_account_id = CASE
                WHEN apm.payment_type = 'inbound'
                    THEN rc.account_journal_payment_debit_account_id
                ELSE rc.account_journal_payment_credit_account_id
            END
        FROM account_payment_method apm, account_journal aj, res_company rc
        WHERE apm.id = apml.payment_method_id
          AND aj.id = apml.journal_id
          AND rc.id = aj.company_id
          AND aj.type IN ('bank', 'cash')
          AND apml.bank_account_link = 'fixed'
          AND apml.payment_account_id IS NULL
        """,
    )


def _set_refund_lines(env):
    cr = env.cr
    if not openupgrade.column_exists(
        cr, "account_payment_mode", "refund_payment_mode_id"
    ):
        logger.warning(
            "No refund_payment_mode_id on account_payment_mode: "
            "skip the migration of the refund payment methods"
        )
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE account_payment_method_line apml
        SET refund_payment_method_line_id = refund_line.id
        FROM account_payment_mode apm, account_payment_method_line refund_line
        WHERE apml.old_payment_mode_id = apm.id
          AND apm.refund_payment_mode_id IS NOT NULL
          AND refund_line.old_payment_mode_id = apm.refund_payment_mode_id
        """,
    )


def _set_move_preferred_payment_method_line(env):
    """Set the preferred payment method line of the invoices from their old
    payment mode."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_move am
        SET preferred_payment_method_line_id = apml.id
        FROM account_payment_mode apm
        JOIN account_payment_method_line apml
            ON apml.old_payment_mode_id = apm.id
        WHERE am.payment_mode_id = apm.id
          AND am.preferred_payment_method_line_id IS NULL
        """,
    )


def _set_partner_payment_method_line(env):
    mapping_expression = """
        (SELECT apml.id
         FROM account_payment_method_line apml
         WHERE apml.old_payment_mode_id = SPLIT_PART(value_reference, ',', 2)::integer
         LIMIT 1)
    """
    for partner_field, old_field_xmlid in (
        (
            "property_outbound_payment_method_line_id",
            "field_res_partner__supplier_payment_mode_id",
        ),
        (
            "property_inbound_payment_method_line_id",
            "field_res_partner__customer_payment_mode_id",
        ),
    ):
        # account_payment_partner is merged into this module: the xmlid has
        # been moved to account_payment_base_oca, but keep a fallback.
        old_field = env.ref(
            f"account_payment_base_oca.{old_field_xmlid}", raise_if_not_found=False
        ) or env.ref(
            f"account_payment_partner.{old_field_xmlid}", raise_if_not_found=False
        )
        if not old_field:
            logger.warning(
                "Field %s not found: skip the conversion of res.partner.%s",
                old_field_xmlid,
                partner_field,
            )
            continue
        openupgrade_180.convert_company_dependent(
            env,
            "res.partner",
            partner_field,
            value_expression=mapping_expression,
            old_field_id=old_field.id,
        )
