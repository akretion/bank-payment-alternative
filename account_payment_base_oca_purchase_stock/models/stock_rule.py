# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _prepare_purchase_order(self, company_id, origins, values):
        """Propagate payment method on MTO/drop shipping."""
        res = super()._prepare_purchase_order(company_id, origins, values)
        values = values[0]
        partner = values["supplier"].partner_id
        if partner:
            res["payment_method_line_id"] = partner.with_company(
                company_id
            ).property_outbound_payment_method_line_id.id
            res["supplier_partner_bank_id"] = self.env[
                "purchase.order"
            ]._get_default_supplier_partner_bank(partner)
        return res
