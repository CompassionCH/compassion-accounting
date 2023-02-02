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

from dateutil.utils import today

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
    pricelist_item_count = fields.Integer(related="product_id.pricelist_item_count", readonly=1)

    @api.depends('amount', 'quantity')
    def _compute_subtotal(self):
        for contract_line in self:
            contract_line.subtotal = contract_line.amount * contract_line.quantity

    @api.onchange('product_id')
    def on_change_product_id(self):
        if not self.product_id:
            self.amount = 0.0
        else:
            self.amount = self.contract_id.pricelist_id.get_product_price(self.product_id,
                                                                          self.quantity,
                                                                          self.contract_id.partner_id,
                                                                          today())

    def build_inv_line_data(self):
        self.ensure_one()
        return self.contract_id.build_inv_line_data(contract_line=self)
