##############################################################################
#
#    Copyright (C) 2014-2022 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, models, fields, _
from odoo.exceptions import UserError


class MoveLine(models.Model):
    """ Adds a method to split a payment into several move_lines
    in order to reconcile only a partial amount, avoiding doing
    partial reconciliation. """

    _inherit = "account.move.line"

    contract_id = fields.Many2one('recurring.contract', 'Source contract', index=True)
    due_date = fields.Date(related='move_id.invoice_date_due', store=True, readonly=True, index=True)
    last_payment = fields.Date(related="move_id.last_payment", store=True)
    payment_state = fields.Selection(related="move_id.payment_state", store=True, readonly=True, index=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        # workaround an odoo bug :
        # could be fixed by applying this change here
        # - self.analytic_tag_ids = rec.analytic_tag_ids.ids
        # + self.analytic_tag_ids = rec.analytic_tag_ids
        # https://github.com/odoo/odoo/blame/12.0/addons/account_analytic_default/models/account_analytic_default.py#L100
        self.analytic_tag_ids = self.env["account.analytic.tag"]
        res = super()._onchange_product_id()
        return res

    def group_reconcile(self, matched_lines, credit_or_debit="debit"):
        """
        Will reconcile the current recordset with any required lines taken from the
        matched_lines recordset. If the sum is not enough, the operation will be aborted.
        :param credit_or_debit: string indicating which amount will be reconciled
        :param matched_lines: <account.move.line> recordset
        :return: True
        """
        to_reconcile = sum(self.mapped(credit_or_debit))
        selected_lines = self.env[self._name]
        reconciled_amount = 0
        inverse_field = "credit" if credit_or_debit == "debit" else "debit"
        for line in matched_lines:
            selected_lines += line
            reconciled_amount += getattr(line, inverse_field)
            if reconciled_amount >= to_reconcile:
                break
        else:
            return False
        return (self | selected_lines).reconcile()

    def _update_invoice_lines_from_contract(self, modified_contract):
        """
        Takes the contract as the source to generate a write command for updating the invoice line
        :param modified_contract: <recurring.contract> record
        :return: list of tuples for ORM write
        """
        res = []
        for invoice_line in self:
            invoice = self.move_id
            cl = modified_contract.contract_line_ids.filtered(lambda l: l.product_id == invoice_line.product_id)
            data_dict = {}
            if cl.product_id.pricelist_item_count > 0:
                price = modified_contract.pricelist_id.get_product_price(
                    cl.product_id, cl.quantity, invoice.partner_id, invoice.invoice_date_due)
                data_dict["price_unit"] = price
                data_dict["quantity"] = cl.quantity
            elif cl:
                data_dict["price_unit"] = cl.amount
                data_dict["quantity"] = cl.quantity
            else:
                raise UserError(_("Unexpected error while updating contract invoices. Please contact admin."))
            # Add the modification on the line
            res.append((1, invoice_line.id, data_dict))
        return res
