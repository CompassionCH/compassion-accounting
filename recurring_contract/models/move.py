##############################################################################
#
#    Copyright (C) 2014-2022 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>, Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################

import html
import logging
from datetime import date

from odoo import fields, models, _, api
from odoo.exceptions import UserError

from .product_names import GIFT_PRODUCTS_REF, PRODUCT_GIFT_CHRISTMAS

class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = 'account.move'

    last_payment = fields.Date(compute="_compute_last_payment", store=True)
    recurring_invoicer_id = fields.Many2one(
        'recurring.invoicer', 'Invoicer', readonly=False
    )

    @api.depends("payment_state")
    def _compute_last_payment(self):
        for invoice in self:
            if invoice.line_ids.full_reconcile_id:
                mv_filter = "credit" if invoice.move_type == "out_invoice" else "debit"
                payment_dates = invoice.line_ids.filtered(mv_filter).mapped(
                    "date"
                )
                invoice.last_payment = max(payment_dates or [False])
            else:
                invoice.last_payment = False

    def register_payment(self, payment_line, writeoff_acc_id=False, writeoff_journal_id=False):
        """After registering a payment post a message of the bank statement linked"""
        out = super().register_payment(payment_line, writeoff_acc_id, writeoff_journal_id)
        self.message_post_bank_statement_notes()
        return out

    def message_post_bank_statement_notes(self):
        """Post a message in the invoice with the messages
        of the bank statement related to this invoice"""
        for invoice in self:
            invoice._message_post_bank_statement_notes()

    def _message_post_bank_statement_notes(self):
        notes = self._get_bank_statement_notes()
        if not notes:
            return
        notes_text = "".join(f"<li>{html.escape(note)}</li>" for note in notes)
        self.message_post(body=_("Notes from bank statement") + f" : <ul>{notes_text}</ul>")

    def _get_bank_statement_notes(self):
        statement_line_ids = self.mapped("line_ids.full_reconcile_id.reconciled_line_ids.statement_line_id")
        return statement_line_ids.filtered("narration").mapped("narration")

    def action_invoice_paid(self):
        """ Call invoice_paid method on related contracts. """
        res = super().action_invoice_paid()
        for invoice in self:
            contracts = invoice.mapped('invoice_line_ids.contract_id')
            contracts.invoice_paid(invoice)
        return res

    def action_invoice_re_open(self):
        """ Call invoice_unpaid method on related contract. """
        res = super().action_invoice_re_open()
        for invoice in self:
            contracts = invoice.mapped('invoice_line_ids.contract_id')
            contracts.invoice_unpaid(invoice)
        return res

    def reconcile_after_clean(self):
        """
        Called after clean invoices. If invoices can be reconciled
        with open payment, this will do it.
        Invoices should be open when called.
        :return: True
        """
        today = date.today()
        mvl_obj = self.env['account.move.line']
        for partner in self.mapped('partner_id'):
            invoices = self.filtered(lambda i: i.partner_id == partner)
            past_invoices = invoices.filtered(lambda i: i.invoice_date_due <= today)
            past_lines = past_invoices.mapped('line_ids').filtered("debit")
            past_amount = sum(past_invoices.mapped('amount_total'))
            future_invoices = invoices - past_invoices
            future_lines = future_invoices.mapped('line_ids').filtered("debit")
            future_amount = sum(future_invoices.mapped('amount_total'))

            # First try to find matching amount payments
            criterias = [
                ('partner_id', '=', partner.id),
                ('account_id', '=', partner.property_account_receivable_id.id),
                ('reconciled', '=', False),
                ("parent_state", "=", "posted")
            ]
            open_payments = mvl_obj.search(criterias + [
                ('credit', 'in', [past_amount, future_amount])
            ])
            for payment in open_payments:
                if past_invoices and payment.credit == past_amount:
                    (past_lines + payment).reconcile()
                    past_invoices = past_invoices.filtered(lambda i: i.payment_state != "paid")
                    future_invoices = future_invoices.filtered(lambda i: i.payment_state != "paid")
                    future_amount = sum(future_invoices.mapped('amount_total'))
                elif future_invoices and payment.credit == future_amount:
                    (future_lines + payment).reconcile()
                    future_invoices = future_invoices.filtered(lambda i: i.payment_state != "paid")

            # If no matching payment found, we will use leftovers with bigger credit.
            if past_invoices:
                past_lines.group_reconcile(mvl_obj.search(criterias))
                future_invoices = future_invoices.filtered(lambda i: i.payment_state != "paid")
            if future_invoices:
                future_lines.group_reconcile(mvl_obj.search(criterias))
        return True

    def update_invoices(self, updt_val):
        """
        It updates the invoices in self with the value of updt_val

        :param updt_val: a dictionary of invoices values with the invoice name
        which refer to another dictionary of values for that invoice name
        """
        for invoice in self.filtered(lambda i: i.invoice_date_due >= date.today()):
            if invoice.name in updt_val:
                val_to_updt = updt_val[invoice.name]
                # In case we modify the amount we want to test if the amount is zero
                invoice.button_draft()
                invoice.update(val_to_updt)
                if invoice.amount_total:
                    invoice.action_post()
                else:
                    invoice.button_cancel()

    def _build_invoice_data(self, contract=False, invoice_date=False, ref=False, pay_mode_id=False,
                            payment_term_id=False, partner_id=False):
        """
        It takes a list of invoice lines, a due date, a payment reference, and a payment mode, and returns a dictionary with
        the invoice lines, the due date, the payment reference, and the payment mode

        :param contract: recurring_contract for which we generate lines (optional)
        :param invoice_date: The date at which the invoice should be accounted, defaults to False (optional)
        :param ref: The reference of the invoice, defaults to False (optional)
        :param pay_mode_id: The payment mode to be used for the invoice, defaults to False (optional)
        :param payment_term_id: payment term id which indicates the offset of the due date.
        :param partner_id: id of a partner in case the partner would have changed (optional)
        :return: A dictionary with the invoice_line_ids, date, payment_reference, and payment_mode_id.
        """
        # Ensure that the funciton receive one invoice
        self.ensure_one()
        # Build the dictionnary
        inv_val_dict = {}
        if contract:
            inv_val_dict["invoice_line_ids"] = self._build_invoice_lines_from_contract(contract)
        if invoice_date:
            inv_val_dict["date"] = invoice_date
        if payment_term_id:
            inv_val_dict["invoice_payment_term_id"] = payment_term_id
        if partner_id:
            inv_val_dict["partner_id"] = partner_id
        if ref:
            inv_val_dict["payment_reference"] = ref
            inv_val_dict["ref"] = ref
        if pay_mode_id:
            inv_val_dict["payment_mode_id"] = pay_mode_id

        return {self.name: inv_val_dict}

    def _build_invoice_lines_from_contract(self, contract):
        """
        It creates a list of tuples that will be used to create, modify or delete invoice lines.

        :param contract recurring_contract that has some modification
        """
        res = []
        line_ids = self.mapped("invoice_line_ids")
        if contract.start_date.date() < self.invoice_date_due:
            # When the invoice isn't a gift we see if a product has been added / deleted
            if any(key not in [GIFT_PRODUCTS_REF[0], PRODUCT_GIFT_CHRISTMAS] for key in line_ids.mapped("product_id.default_code")):
                # Line to delete in the invoice
                # If the invoice has different product than the contract we should delete the line
                contract_products = contract.contract_line_ids.mapped("product_id")
                diff_product_lines = line_ids.filtered(lambda l: l.product_id not in contract_products)
                res.extend([(2, line.id, 0) for line in diff_product_lines])
                # Line to create in the invoice
                # If the contract has different product than the invoice we should create the line
                missing_lines = contract.contract_line_ids.filtered(lambda l: l.product_id not in line_ids.mapped("product_id"))
                res.extend([(0, 0, line_vals.build_inv_line_data()) for line_vals in missing_lines])
                # Line to modify in the invoice
                line_ids = line_ids.filtered(lambda l: l.product_id.id not in missing_lines.mapped("product_id").ids
                                                       and l.id not in diff_product_lines.ids)

            # Modification on invoices
            for line_id in line_ids:
                cl = contract.contract_line_ids.filtered(lambda l: l.product_id == line_id.product_id)
                data_dict = {}
                # Process specific cases for gift
                if line_id.product_id.default_code == PRODUCT_GIFT_CHRISTMAS:
                    data_dict["price_unit"] = contract.christmas_invoice
                elif line_id.product_id.default_code == GIFT_PRODUCTS_REF[0]:
                    data_dict["price_unit"] = contract.birthday_invoice
                elif cl.product_id.pricelist_item_count > 0:
                    price = contract.pricelist_id.get_product_price(cl.product_id,
                                                                    cl.quantity,
                                                                    self.partner_id,
                                                                    self.invoice_date_due)
                    data_dict["price_unit"] = price
                    data_dict["quantity"] = cl.quantity
                elif cl:
                    data_dict["price_unit"] = cl.amount
                    data_dict["quantity"] = cl.quantity
                else:
                    raise UserError("Case not supposed to happen :) contact admin.")
                # Add the modification on the line
                res.append((1, line_id.id, data_dict))
        return res
