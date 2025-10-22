# © 2023 Akretion (<https://www.akretion.com>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class AccountPaymentLineCreate(models.TransientModel):
    _inherit = "account.payment.line.create"

    currency_ids = fields.Many2many(
        comodel_name="res.currency", string="Currency Filter"
    )

    @api.model
    def default_get(self, field_list):
        res = super().default_get(field_list)
        context = self.env.context
        order = self.env["account.payment.order"].browse(context["active_id"])
        method_line = order.payment_method_line_id
        res.update(
            {
                "currency_ids": method_line.default_currency_ids,
            }
        )
        return res

    def _prepare_move_line_domain(self):
        res = super()._prepare_move_line_domain()
        if self.currency_ids:
            res += [("currency_id", "in", self.currency_ids.ids)]
        return res

    @api.depends("currency_ids")
    def _compute_eligible_move_line_ids(self):
        return super()._compute_eligible_move_line_ids()
