# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import Command, fields
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestPaymentOrderSelectForPayment(AccountTestInvoicingCommon):
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
                "default_selected_for_payment": True,
            }
        )

        cls.payment_order = cls.env["account.payment.order"].create(
            {
                "payment_method_line_id": cls.method_line.id,
                "payment_type": "outbound",
                "journal_id": cls.company_data["default_journal_bank"].id,
            }
        )

        cls.invoice_topay = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (0, 0, {"name": "Test line 1", "quantity": 1, "price_unit": 100.0})
                ],
            }
        )

        cls.invoice_not_topay = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.partner_a.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (0, 0, {"name": "Test line 2", "quantity": 1, "price_unit": 50.0})
                ],
            }
        )

        (cls.invoice_topay | cls.invoice_not_topay).action_post()
        cls.invoice_topay.write({"selected_for_payment": True})

        cls.topay_line = cls.invoice_topay.line_ids.filtered(
            lambda line: line.account_id.account_type == "liability_payable"
        )
        cls.not_topay_line = cls.invoice_not_topay.line_ids.filtered(
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

        # default wizard has the selected for payment option
        wizard.populate()
        self.assertIn(self.topay_line, wizard.move_line_ids)
        self.assertNotIn(self.not_topay_line, wizard.move_line_ids)

        wizard.select_for_payment_filter = False
        wizard.populate()
        self.assertIn(self.topay_line, wizard.move_line_ids)
        self.assertIn(self.not_topay_line, wizard.move_line_ids)
