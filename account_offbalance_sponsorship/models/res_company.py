from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    off_balance_asset_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Off-Balance Asset Account",
        help="Account used for off-balance asset management.",
        domain=[("is_off_balance", "=", True), ("account_type", "like", "asset")],
    )
