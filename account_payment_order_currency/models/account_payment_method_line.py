# © 2023 Akretion (<https://www.akretion.com>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class AccountPaymentMethodLine(models.Model):
    _inherit = "account.payment.method.line"

    default_currency_ids = fields.Many2many(
        comodel_name="res.currency",
        string="Currency Filter",
    )
