# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import Command
from odoo.tests import Form, TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("-at_install", "post_install")
class TestAccountPaymentBaseOCAPurchase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.env.ref("base.main_company")
        cls.company_bank = cls.env["res.partner.bank"].create(
            {
                "acc_number": "FR66 1234 5678 1212 6363 3636 098",
                "partner_id": cls.company.partner_id.id,
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Test journal",
                "code": "TEST",
                "type": "bank",
                "company_id": cls.company.id,
                "bank_account_id": cls.company_bank.id,
            }
        )
        cls.payment_method_out = cls.env.ref(
            "account.account_payment_method_manual_out"
        )
        cls.payment_method_out.bank_account_required = True
        cls.payment_method_line = cls.env["account.payment.method.line"].create(
            {
                "name": "Test payment method",
                "payment_method_id": cls.payment_method_out.id,
                "bank_account_link": "fixed",
                "journal_id": cls.journal.id,
                "selectable": True,
            }
        )
        cls.payment_method_line2 = cls.env["account.payment.method.line"].create(
            {
                "name": "Test payment method #2",
                "payment_method_id": cls.payment_method_out.id,
                "bank_account_link": "fixed",
                "journal_id": cls.journal.id,
                "selectable": True,
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test partner",
                "property_outbound_payment_method_line_id": cls.payment_method_line.id,
            }
        )
        cls.bank = cls.env["res.partner.bank"].create(
            {
                "bank_name": "Test bank",
                "acc_number": "1234567890",
                "partner_id": cls.partner.id,
                "allow_out_payment": True,
            }
        )
        cls.bank2 = cls.env["res.partner.bank"].create(
            {
                "bank_name": "Test bank #2",
                "acc_number": "0123456789",
                "partner_id": cls.partner.id,
            }
        )
        cls.uom_id = cls.env.ref("uom.product_uom_unit").id
        cls.mto_product = cls.env["product.product"].create(
            {
                "name": "Test buy product",
                "uom_id": cls.uom_id,
                "uom_po_id": cls.uom_id,
                "seller_ids": [Command.create({"partner_id": cls.partner.id})],
            }
        )
        order_form = Form(cls.env["purchase.order"])
        order_form.partner_id = cls.partner
        with order_form.order_line.new() as line_form:
            line_form.product_id = cls.mto_product
            line_form.product_qty = 1
        cls.purchase = order_form.save()

    def test_onchange_partner_id_purchase_order(self):
        self.assertEqual(self.purchase.payment_method_line_id, self.payment_method_line)

    @mute_logger("odoo.models.unlink")
    def test_purchase_order_create_invoice(self):
        self.purchase.button_confirm()
        self.purchase.order_line.qty_received = 1
        res = self.purchase.action_create_invoice()
        invoice = self.env[res["res_model"]].browse(res["res_id"])
        self.assertEqual(
            invoice.preferred_payment_method_line_id, self.payment_method_line
        )
        self.assertEqual(invoice.partner_bank_id, self.bank)
        # Remove the invoice and try another use case
        invoice.unlink()
        self.payment_method_out.bank_account_required = False
        res = self.purchase.action_create_invoice()
        invoice2 = self.env[res["res_model"]].browse(res["res_id"])
        self.assertFalse(invoice2.partner_bank_id)

    def test_purchase_order_invoicing(self):
        self.purchase.button_confirm()
        invoice = self.env["account.move"].create(
            {"partner_id": self.partner.id, "move_type": "in_invoice"}
        )
        invoice.purchase_id = self.purchase
        invoice._onchange_purchase_auto_complete()
        self.assertEqual(
            invoice.preferred_payment_method_line_id, self.payment_method_line
        )

    def test_from_purchase_order_invoicing(self):
        # Test payment method
        product = self.env["product.product"].create({"name": "Test product"})
        self.purchase.order_line[0].product_id = product
        self.purchase.button_confirm()

        invoice = self.env["account.move"].create(
            {"partner_id": self.partner.id, "move_type": "in_invoice"}
        )
        invoice.purchase_id = self.purchase
        invoice._onchange_purchase_auto_complete()
        self.assertEqual(
            invoice.preferred_payment_method_line_id, self.payment_method_line
        )
        purchase2 = self.purchase.copy()
        purchase2.payment_method_line_id = self.payment_method_line2
        purchase2.button_confirm()

        invoice.purchase_id = purchase2
        result = invoice._onchange_purchase_auto_complete()
        self.assertEqual(
            result and result.get("warning", {}).get("title", False), "Warning"
        )

    def test_from_purchase_order_invoicing_bank(self):
        # Test supplier bank
        product = self.env["product.product"].create({"name": "Test product"})
        self.purchase.order_line[0].product_id = product
        self.purchase.supplier_partner_bank_id = self.bank
        self.purchase.button_confirm()
        invoice = self.env["account.move"].create(
            {"partner_id": self.partner.id, "move_type": "in_invoice"}
        )
        invoice.purchase_id = self.purchase
        invoice._onchange_purchase_auto_complete()
        self.assertEqual(invoice.partner_bank_id, self.bank)
        purchase2 = self.purchase.copy()
        purchase2.supplier_partner_bank_id = self.bank2
        purchase2.button_confirm()

        invoice.purchase_id = purchase2
        result = invoice._onchange_purchase_auto_complete()
        self.assertEqual(
            result and result.get("warning", {}).get("title", False), "Warning"
        )
