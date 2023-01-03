##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

import logging


from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ContractLine(models.Model):
    """ Each product sold through a contract """

    _name = "recurring.contract.line"
    _description = "Recurring contract line"

    def name_get(self):
        res = [(cl.id, cl.product_id.name) for cl in self]
        return res

    contract_id = fields.Many2one(
        'recurring.contract', 'Contract', required=True,
        ondelete='cascade', readonly=True)
    product_id = fields.Many2one('product.product', 'Product',
                                 required=True, readonly=False)
    amount = fields.Float('Price', required=True)
    quantity = fields.Integer(default=1, required=True)
    subtotal = fields.Float(compute='_compute_subtotal', store=True,
                            digits='Account')

    @api.depends('amount', 'quantity')
    def _compute_subtotal(self):
        for contract in self:
            contract.subtotal = contract.amount * contract.quantity

    @api.onchange('product_id')
    def on_change_product_id(self):
        if not self.product_id:
            self.amount = 0.0
        else:
            self.amount = self.product_id.list_price

    def build_inv_line_data(self):
        self.ensure_one()
        return {
                    "price_unit": self.amount,
                    "product_id": self.product_id.id,
                    'name': self.product_id.name,
                    'quantity': self.quantity,
                    'contract_id': self.contract_id.id,
                    'account_id': self.product_id.with_company(
                        self.contract_id.company_id.id).property_account_income_id.id or False
                }