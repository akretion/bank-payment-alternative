# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    env.cr.execute("""
        INSERT INTO account_payment_method_line_res_currency_rel
            (account_payment_method_line_id, res_currency_id)
        SELECT
            t2.id,
            t1.res_currency_id
        FROM
            account_payment_mode_res_currency_rel AS t1
        JOIN
            account_payment_method_line AS t2
            ON t1.account_payment_mode_id = t2.old_payment_mode_id;
    """)
