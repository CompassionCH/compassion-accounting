from odoo import models, _


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    def update_cl_amount(self):
        for item in self:
            contract_lines = self.env['recurring.contract.line'].search([
                ('contract_id.pricelist_id', '=', item.pricelist_id.id),
                ('product_id', '=', item.product_id.id),
                ('contract_id.state', 'not in', ['cancelled', 'terminated'])
            ])
            for cl in contract_lines:
                price = cl.contract_id.pricelist_id.get_product_price(cl.product_id,
                                                                      cl.quantity,
                                                                      cl.contract_id.partner_id)
                if cl.amount != price:
                    cl.amount = price
        return {
            'type': 'ir.actions.client',
            'tag': 'notification',
            'params': {
                'title': _('Contract Line Prices Updated'),
                'message': _('The prices of the contract lines associated with this pricelist item have been updated.'),
                'sticky': True,
            }
        }
