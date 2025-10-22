# © 2023 Akretion (<https://www.akretion.com>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class AccountPaymentLineCreate(models.TransientModel):
    _inherit = "account.payment.line.create"

    select_for_payment_filter = fields.Boolean(
        string="Take only to pay",
        store=True,
        readonly=False,
    )

    @api.model
    def default_get(self, field_list):
        res = super().default_get(field_list)
        context = self.env.context
        order = self.env["account.payment.order"].browse(context["active_id"])
        method_line = order.payment_method_line_id
        res.update(
            {
                "select_for_payment_filter": method_line.default_selected_for_payment,
            }
        )
        return res

    def _prepare_move_line_domain(self):
        res = super()._prepare_move_line_domain()

        if self.select_for_payment_filter:
            res += [("move_id.selected_for_payment", "=", True)]
        return res

    @api.depends("select_for_payment_filter")
    def _compute_eligible_move_line_ids(self):
        return super()._compute_eligible_move_line_ids()
