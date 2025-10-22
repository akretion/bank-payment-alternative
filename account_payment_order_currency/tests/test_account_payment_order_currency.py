# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import Command, fields
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestPaymentOrderCurrency(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.write(
            {
                "groups_id": [
                    Command.link(
                        cls.env.ref(
                            "account_payment_batch_oca.group_account_payment"
                        ).id
                    )
                ]
            }
        )
        cls.usd = cls.env.ref("base.USD")
        cls.eur = cls.env.ref("base.EUR")
        cls.eur.active = True
        cls.payment_method_manual_out = cls.env.ref(
            "account.account_payment_method_manual_out"
        )

        cls.method_line = cls.env["account.payment.method.line"].create(
            {
                "name": "Test Filter Currency",
                "payment_method_id": cls.payment_method_manual_out.id,
                "payment_type": "outbound",
                "payment_order_ok": True,
                "selectable": True,
                "bank_account_link": "fixed",
                "journal_id": cls.company_data["default_journal_bank"].id,
                "default_currency_ids": [Command.set(cls.eur.ids)],
            }
        )

        cls.payment_order = cls.env["account.payment.order"].create(
            {
                "payment_method_line_id": cls.method_line.id,
                "payment_type": "outbound",
                "journal_id": cls.company_data["default_journal_bank"].id,
            }
        )

        cls.invoice_eur = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.partner_a.id,
                "currency_id": cls.eur.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (0, 0, {"name": "Euro line", "quantity": 1, "price_unit": 100.0})
                ],
            }
        )

        cls.invoice_usd = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.partner_a.id,
                "currency_id": cls.usd.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (0, 0, {"name": "USD line", "quantity": 1, "price_unit": 50.0})
                ],
            }
        )

        (cls.invoice_eur | cls.invoice_usd).action_post()

        cls.euro_line = cls.invoice_eur.line_ids.filtered(
            lambda line: line.account_id.account_type == "liability_payable"
        )
        cls.usd_line = cls.invoice_usd.line_ids.filtered(
            lambda line: line.account_id.account_type == "liability_payable"
        )

        cls.wizard_model = cls.env["account.payment.line.create"]

    def test_01_wizard_filter_currency(self):
        wizard = self.wizard_model.with_context(
            active_model="account.payment.order", active_id=self.payment_order.id
        ).create({})

        wizard.partner_ids = [Command.set(self.partner_a.ids)]
        wizard.payment_mode = "any"
        wizard.due_date = fields.Date.today()

        #       # default currency on wizard is EURO
        wizard.populate()
        self.assertIn(self.euro_line, wizard.move_line_ids)
        self.assertNotIn(self.usd_line, wizard.move_line_ids)

        wizard.currency_ids = [Command.set(self.usd.ids)]
        wizard.populate()
        self.assertNotIn(self.euro_line, wizard.move_line_ids)
        self.assertIn(self.usd_line, wizard.move_line_ids)

        wizard.currency_ids = [Command.set([self.eur.id, self.usd.id])]
        wizard.populate()
        self.assertIn(self.euro_line, wizard.move_line_ids)
        self.assertIn(self.usd_line, wizard.move_line_ids)

        wizard.currency_ids = [Command.clear()]
        wizard.populate()
        self.assertIn(self.euro_line, wizard.move_line_ids)
        self.assertIn(self.usd_line, wizard.move_line_ids)
