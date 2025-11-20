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

    def _search(self, domain, offset=0, limit=None, order=None):
        if self.env.context.get("filter_off_balance"):
            domain.append(("is_off_balance", "=", False))
        return super()._search(domain, offset, limit, order)
