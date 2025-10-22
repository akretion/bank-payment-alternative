# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    env.cr.execute("""
        UPDATE account_payment_method_line
        SET default_selected_for_payment = apm.default_selected_for_payment
        FROM account_payment_mode apm
        WHERE apm.id = account_payment_method_line.old_payment_mode_id
    """)
