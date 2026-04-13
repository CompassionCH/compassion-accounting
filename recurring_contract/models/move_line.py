##############################################################################
#
#    Copyright (C) 2014-2022 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MoveLine(models.Model):
    """Adds a method to split a payment into several move_lines
    in order to reconcile only a partial amount, avoiding doing
    partial reconciliation."""

    _inherit = "account.move.line"

    contract_id = fields.Many2one(
        "recurring.contract",
        "Source contract",
        index=True,
        domain="[('partner_id', '=', parent.partner_id), "
        "('state', 'in', ['draft', 'active'])]",
    )
    due_date = fields.Date(
        related="move_id.invoice_date_due", store=True, readonly=True, index=True
    )
    last_payment = fields.Date(
        related="move_id.last_payment", store=True, readonly=True
    )
    payment_state = fields.Selection(
        related="move_id.payment_state", store=True, readonly=True, index=True
    )
    reconciled_contract_lines = fields.Many2many(
        "account.move.line",
        compute="_compute_reconciled_contract_lines",
        help="Lookup for all related reconciled move lines attached to a contract.",
    )

    @api.depends("matched_credit_ids", "matched_debit_ids")
    def _compute_reconciled_contract_lines(self):
        for line in self:
            line.reconciled_contract_lines = self.browse(
                (
                    line.matched_debit_ids.debit_move_id
                    | line.matched_credit_ids.credit_move_id
                ).move_id.line_ids._reconciled_lines()
            ).move_id.line_ids.filtered("contract_id")

    def group_reconcile(self, matched_lines, credit_or_debit="debit"):
        """
        Will reconcile the current recordset with any required lines taken from the
        matched_lines recordset.
        If the sum is not enough, the operation will be aborted.
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
        Takes the contract as the source to generate a write command for updating
        the invoice lines
        :param modified_contract: <recurring.contract> record
        :return: list of tuples for ORM write
        """
        modified_contract.ensure_one()
        res = []
        for invoice_line in self:
            invoice = self.move_id
            contract_line = modified_contract.contract_line_ids.filtered(
                lambda cl, invl=invoice_line: cl.product_id == invl.product_id
            )
            data_dict = {}
            if contract_line.product_id.pricelist_item_count > 0:
                price = modified_contract.pricelist_id._get_product_price(
                    contract_line.product_id,
                    quantity=contract_line.quantity,
                    date=invoice.invoice_date,
                )
                data_dict["price_unit"] = price
                data_dict["quantity"] = contract_line.quantity
            elif contract_line:
                data_dict["price_unit"] = contract_line.amount
                data_dict["quantity"] = contract_line.quantity
            else:
                raise UserError(_("Unexpected error while updating contract invoices."))
            # Add the modification on the line
            res.append((1, invoice_line.id, data_dict))
        return res

    def _reconcile_post_hook(self, data):
        """
        When a direct debit is reconciled, the linked invoice is paid.
        We need to trigger the invoice_paid method on the contract.
        """
        res = super()._reconcile_post_hook(data)
        # Find invoices that are part of the reconciliation and are now paid.
        invoices = self.reconciled_contract_lines.move_id.filtered(
            lambda m: m.is_invoice(include_receipts=True) and m.payment_state == "paid"
        )
        for invoice in invoices:
            contracts = invoice.mapped("line_ids.contract_id")
            contracts.invoice_paid(invoice)
        return res
