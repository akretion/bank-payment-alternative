#  License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from openupgradelib import openupgrade

from odoo.fields import first


@openupgrade.migrate()
def migrate(env, version):
    # payment_order_ok was on the payment method in v16, but with the opposite
    # meaning ("only for payment orders"). The field which said if a payment
    # mode can be used in a payment order was on the payment mode: a payment
    # method is usable in payment orders if at least one of its payment modes
    # was.
    env.cr.execute("""
        UPDATE account_payment_method apm
        SET payment_order_ok = TRUE
        WHERE EXISTS (
            SELECT 1
            FROM account_payment_mode apm_v16
            WHERE apm_v16.payment_method_id = apm.id
              AND apm_v16.payment_order_ok
        )
    """)
    env.cr.execute("""
        UPDATE account_payment_method_line
        SET payment_order_ok = apm.payment_order_ok,
            no_debit_before_maturity = apm.no_debit_before_maturity,
            default_payment_mode = apm.default_payment_mode,
            default_invoice = apm.default_invoice,
            default_target_move = apm.default_target_move,
            default_date_type = apm.default_date_type,
            default_date_prefered = apm.default_date_prefered,
            group_lines = apm.group_lines
        FROM account_payment_mode apm
        WHERE account_payment_method_line.old_payment_mode_id IS NOT NULL
        AND apm.id = account_payment_method_line.old_payment_mode_id
    """)
    # the lines which don't replace a payment mode are not selectable on
    # partners/invoices, so they can't be selected on a payment order either
    env.cr.execute("""
        UPDATE account_payment_method_line
        SET payment_order_ok = FALSE
        WHERE selectable IS NOT TRUE
    """)
    # manage default_journal_ids
    # remove default computed values of the new method lines
    env.cr.execute("DELETE FROM account_journal_account_payment_method_line_rel")
    # fill from old payment mode table
    env.cr.execute("""
        INSERT INTO account_journal_account_payment_method_line_rel
            (account_payment_method_line_id, account_journal_id)
        SELECT
            t2.id,
            t1.account_journal_id
        FROM
            account_journal_account_payment_mode_rel AS t1
        JOIN
            account_payment_method_line AS t2
            ON t1.account_payment_mode_id = t2.old_payment_mode_id;
    """)

    env.cr.execute("""
        UPDATE account_payment_order
        SET payment_method_line_id = apml.id,
            payment_method_code = account_payment_method.code
        FROM account_payment_method_line apml,
             account_payment_mode apm,
             account_payment_method
        WHERE account_payment_order.payment_mode_id = apm.id
        AND apml.old_payment_mode_id = apm.id
        AND account_payment_method.id = apml.payment_method_id
    """)

    env.cr.execute(
        "UPDATE account_move SET reference_type='free' WHERE reference_type='none'"
    )
    env.cr.execute(
        "UPDATE account_payment_line SET communication_type='free' "
        "WHERE communication_type='normal'"
    )

    # generate lot for confirmed payment orders
    for order in env["account.payment.order"].search([("state", "=", "open")]):
        lots = {}
        for payment in order.payment_ids:
            payment_line = first(payment.payment_line_ids)
            if not payment_line:
                continue
            lot_key = payment_line._lot_grouping_key()
            if lot_key not in lots:
                lots[lot_key] = env["account.payment.lot"].create(
                    payment_line._prepare_account_payment_lot_vals(len(lot_key) + 1)
                )
            payment.write({"payment_lot_id": lots[lot_key].id})
