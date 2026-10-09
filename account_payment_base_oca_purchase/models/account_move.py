# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.depends("bank_partner_id", "preferred_payment_method_line_id")
    def _compute_partner_bank_id(self):
        res = super()._compute_partner_bank_id()
        for move in self.filtered(lambda m: m.is_purchase_document()):
            payment_method = move.preferred_payment_method_line_id.payment_method_id
            if payment_method and not payment_method.bank_account_required:
                move.partner_bank_id = False
        return res

    @api.onchange("purchase_vendor_bill_id", "purchase_id")
    def _onchange_purchase_auto_complete(self):
        old_method = self.preferred_payment_method_line_id.id
        old_bank = self.partner_bank_id.id
        purchase_id = self.purchase_vendor_bill_id.purchase_order_id or self.purchase_id
        if purchase_id:
            new_invoice_vals = purchase_id.with_company(
                purchase_id.company_id
            )._prepare_invoice()
            new_method = new_invoice_vals.get("preferred_payment_method_line_id", False)
            new_bank = new_invoice_vals.get("partner_bank_id", False)
        else:
            new_method = new_bank = False

        res = super()._onchange_purchase_auto_complete() or {}
        if old_method and new_method and old_method != new_method:
            res["warning"] = {
                "title": self.env._("Warning"),
                "message": self.env._(
                    "Selected purchase order have different payment method."
                ),
            }
            return res
        elif new_method and self.preferred_payment_method_line_id.id != new_method:
            self.preferred_payment_method_line_id = new_method
        if old_bank and new_bank and old_bank != new_bank:
            res["warning"] = {
                "title": self.env._("Warning"),
                "message": self.env._(
                    "Selected purchase order have different supplier bank."
                ),
            }
        elif new_bank and self.partner_bank_id.id != new_bank:
            self.partner_bank_id = new_bank
        return res
