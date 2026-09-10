from odoo import fields, models


class AccountReconcileModel(models.Model):
    _inherit = "account.reconcile.model.line"

    product_id = fields.Many2one("product.product")

    def _get_write_off_move_line_dict(self, balance, currency):
        vals = super()._get_write_off_move_line_dict(balance, currency)
        vals["product_id"] = self.product_id.id
        return vals
