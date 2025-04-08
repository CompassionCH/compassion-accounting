from odoo import api, fields, models


class Account(models.Model):
    _inherit = "account.account"

    is_off_balance = fields.Boolean()
    on_balance_account_id = fields.Many2one(
        "account.account",
        string="Linked On-Balance Account",
    )

    @api.onchange("is_off_balance")
    def onchange_is_off_balance(self):
        """
        Set the linked on-balance account to False if the off-balance account is
        unchecked.
        """
        if not self.is_off_balance:
            self.on_balance_account_id = False
