# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import fields

from odoo.addons.account_payment_base_oca_purchase.tests.test_account_payment_base_oca_purchase import (  # noqa: E501
    TestAccountPaymentBaseOCAPurchase,
)


class TestAccountPaymentBaseOCAPurchaseStock(TestAccountPaymentBaseOCAPurchase):
    def _set_stockable_product(self):
        stockable_product = self.env["product.product"].create(
            {"name": "Test stockable product", "type": "consu", "is_storable": True}
        )
        self.purchase.order_line[0].product_id = stockable_product

    def test_purchase_stock_order_invoicing(self):
        self._set_stockable_product()
        self.purchase.button_confirm()
        picking = self.purchase.picking_ids[0]
        picking.action_confirm()
        picking.button_validate()

        invoice = self.env["account.move"].create(
            {"partner_id": self.partner.id, "move_type": "in_invoice"}
        )
        invoice.purchase_id = self.purchase
        invoice._onchange_purchase_auto_complete()
        self.assertEqual(
            invoice.preferred_payment_method_line_id, self.payment_method_line
        )

    def test_picking_from_purchase_order_invoicing(self):
        # Test payment method
        self._set_stockable_product()
        self.purchase.button_confirm()
        picking = self.purchase.picking_ids[0]
        picking.action_confirm()
        picking.button_validate()

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
        picking = purchase2.picking_ids[0]
        picking.action_confirm()
        picking.button_validate()
        invoice.purchase_id = purchase2
        result = invoice._onchange_purchase_auto_complete()
        self.assertEqual(
            result and result.get("warning", {}).get("title", False), "Warning"
        )

    def test_picking_from_purchase_order_invoicing_bank(self):
        # Test supplier bank
        self._set_stockable_product()
        self.purchase.supplier_partner_bank_id = self.bank
        self.purchase.button_confirm()
        picking = self.purchase.picking_ids[0]
        picking.action_confirm()
        picking.button_validate()

        invoice = self.env["account.move"].create(
            {"partner_id": self.partner.id, "move_type": "in_invoice"}
        )
        invoice.purchase_id = self.purchase
        invoice._onchange_purchase_auto_complete()
        self.assertEqual(invoice.partner_bank_id, self.bank)
        purchase2 = self.purchase.copy()
        purchase2.supplier_partner_bank_id = self.bank2
        purchase2.button_confirm()
        picking = purchase2.picking_ids[0]
        picking.action_confirm()
        picking.button_validate()
        invoice.purchase_id = purchase2
        result = invoice._onchange_purchase_auto_complete()
        self.assertEqual(
            result and result.get("warning", {}).get("title", False), "Warning"
        )

    def test_stock_rule_buy_payment_method(self):
        route = self.env.ref("purchase_stock.route_warehouse0_buy")
        rule = self.env["stock.rule"].search([("route_id", "=", route.id)], limit=1)
        rule._run_buy(
            procurements=[
                (
                    self.env["procurement.group"].Procurement(
                        self.mto_product,
                        1,
                        self.mto_product.uom_id,
                        self.env["stock.location"].search([], limit=1),
                        "Procurement order test",
                        "Test",
                        rule.company_id,
                        {
                            "company_id": rule.company_id,
                            "date_planned": fields.Datetime.now(),
                        },
                    ),
                    rule,
                )
            ]
        )
        purchase = self.env["purchase.order"].search([("origin", "=", "Test")])
        self.assertEqual(purchase.payment_method_line_id, self.payment_method_line)
