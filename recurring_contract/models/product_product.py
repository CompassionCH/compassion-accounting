from odoo import models, fields


class ProductProduct(models.Model):
    _inherit = 'product.product'

    contract_line_ids = fields.One2many(
        'recurring.contract.line',
        inverse_name='product_id',
        string='Contract Lines',
        readonly=True
    )
