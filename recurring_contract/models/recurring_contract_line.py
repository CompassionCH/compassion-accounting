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
from datetime import datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ContractLine(models.Model):
    """Each product sold through a contract"""

    _name = "recurring.contract.line"
    _description = "Recurring contract line"

    def write(self, vals):
        super().write(vals)
        self._updt_invoices_rcl(vals)

    def name_get(self):
        res = [(cl.id, cl.product_id.name) for cl in self]
        return res

    contract_id = fields.Many2one(
        "recurring.contract",
        "Contract",
        required=True,
        ondelete="cascade",
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product", "Product", required=True, readonly=False
    )
    amount = fields.Float("Price", required=True)
    quantity = fields.Integer(default=1, required=True)
    subtotal = fields.Float(compute="_compute_subtotal", store=True)
    pricelist_item_count = fields.Integer(
        related="product_id.pricelist_item_count", readonly=1
    )

    _sql_constraints = [
        (
            "unique_product_per_contract",
            "UNIQUE(contract_id,product_id)",
            "You cannot set two lines with the same product.",
        )
    ]

    @api.depends("amount", "quantity")
    def _compute_subtotal(self):
        for contract_line in self:
            contract_line.subtotal = contract_line.amount * contract_line.quantity

    @api.onchange("product_id")
    def on_change_product_id(self):
        for line in self.filtered("product_id"):
            line.amount = line.contract_id.pricelist_id.get_product_price(
                line.product_id,
                line.quantity,
                line.contract_id.partner_id,
                datetime.now(),
            )

    def build_inv_line_data(self):
        self.ensure_one()
        return self.contract_id.group_id.build_inv_line_data(contract_line=self)

    def _updt_invoices_rcl(self, vals):
        """
        It updates the invoices of a contract when the contract is updated

        :param vals: the values that are being updated on the contract
        """
        data_invs = {}
        if (
            "product" in vals
            or "amount" in vals
            or "quantity" in vals
            or "contract_id" in vals
        ):
            data_invs = self.mapped(
                "contract_id.open_invoice_ids"
            )._build_invoices_data(contracts=self.mapped("contract_id"))
            self.mapped("contract_id.open_invoice_ids").update_open_invoices(data_invs)
