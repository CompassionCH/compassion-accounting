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

from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = 'account.move'

    recurring_invoicer_id = fields.Many2one(
        'recurring.invoicer', 'Invoicer', readonly=False)

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
        with open payment, this will split the payment into three amounts :
            - amount for reconciling the past invoices
            - amount for reconciling the future invoices
            - leftover amount that will stay in the client balance
        Then the invoices will be reconciled again

        Invoices should be opened or canceled. if they are canceled they will
        first be reopened
        :return: True
        """
        # At first we open again the cancelled invoices
        cancel_invoices = self.filtered(lambda i: i.state == 'cancel')
        cancel_invoices.button_draft()
        cancel_invoices.action_post()
        today = date.today()
        for partner in self.mapped('partner_id'):
            invoices = self.filtered(lambda i: i.partner_id == partner)
            past_invoices = invoices.filtered(lambda i: i.invoice_date <= today)
            future_invoices = invoices - past_invoices
            past_amount = sum(past_invoices.mapped('amount_total'))
            future_amount = sum(future_invoices.mapped('amount_total'))
            is_past_reconciled = not past_invoices
            is_future_reconciled = not future_invoices

            # First try to find matching amount payments
            open_payments = self.env['account.move.line'].search([
                ('partner_id', '=', partner_id),
                ('account_id.code', '=', '1050'),
                ('reconciled', '=', False),
                ('credit', 'in', [past_amount, future_amount])
            ])
            for payment in open_payments:
                if not is_past_reconciled and payment.credit == past_amount:
                    lines = past_invoices.mapped('line_ids').filtered("debit")
                    (lines + payment).reconcile()
                    is_past_reconciled = True
                elif not is_future_reconciled and payment.credit == future_amount:
                    lines = future_invoices.mapped('line_ids').filtered("debit")
                    (lines + payment).reconcile()
                    is_future_reconciled = True

            # If no matching payment found, we will group or split.
            if not is_past_reconciled:
                past_invoices.with_delay()._group_or_split_reconcile()
            if not is_future_reconciled:
                future_invoices.with_delay()._group_or_split_reconcile()

        return True

    def _group_or_split_reconcile(self):
        """
        Find payments to reconcile given invoices and perform reconciliation.
        :return: True
        """
        partner = self.mapped('partner_id')
        partner.ensure_one()
        reconcile_amount = sum(self.mapped('amount_total'))
        move_lines = self.mapped('line_ids').filtered('debit')
        payment_search = [
            ('partner_id', '=', partner.id),
            ('account_id.code', '=', '1050'),
            ('reconciled', '=', False),
            ('credit', '>', 0)
        ]

        line_obj = self.env['account.move.line']
        payment_greater_than_reconcile = line_obj.search(
            payment_search + [('credit', '>', reconcile_amount)],
            order='date asc', limit=1)
        if payment_greater_than_reconcile:
            # Split the payment move line to isolate reconcile amount
            return (payment_greater_than_reconcile | move_lines) \
                .split_payment_and_reconcile()
        else:
            # Group several payments to match the invoiced amount
            # Limit to 12 move_lines to avoid too many computations
            open_payments = line_obj.search(payment_search, limit=12)
            if sum(open_payments.mapped("credit")) < reconcile_amount:
                raise UserError(_("Cannot reconcile invoices, not enough credit."))

            # Search for a combination giving the invoiced amount recursively
            # https://stackoverflow.com/questions/4632322/finding-all-possible-
            # combinations-of-numbers-to-reach-a-given-sum
            def find_sum(numbers, target, partial=None):
                if partial is None:
                    partial = []
                s = sum(p.credit for p in partial)

                if s == target:
                    return partial
                if s >= target:
                    return  # if we reach the number why bother to continue

                for i in range(len(numbers)):
                    ret = find_sum(numbers[i + 1:], target,
                                   partial + [numbers[i]])
                    if ret is not None:
                        return ret

            matching_lines = line_obj
            sum_found = find_sum(open_payments, reconcile_amount)
            if sum_found is not None:
                for payment in sum_found:
                    matching_lines += payment
                return (matching_lines | move_lines).reconcile()
            else:
                # No combination found: we must split one payment
                payment_amount = 0
                for index, payment_line in enumerate(open_payments):
                    missing_amount = reconcile_amount - payment_amount
                    if payment_line.credit > missing_amount:
                        # Split last added line amount to perfectly match
                        # the total amount we are looking for
                        return (open_payments[:index + 1] | move_lines) \
                            .split_payment_and_reconcile()
                    payment_amount += payment_line.credit
                return (open_payments | move_lines).reconcile()

    def update_invoices(self, updt_val):
        """
        It updates the invoices in self with the value of updt_val

        :param updt_val: a dictionary of invoices values with the invoice name
        which refer to another dictionnary of values for that invoice name
        """
        if updt_val:
            for invoice in self:
                # Retrieve the value for a specific invoice
                try:
                    val_to_updt = updt_val.get(invoice.name)
                except KeyError:
                    logging.getLogger(__name__).warning(f"No key in the dictionnary for invoice {invoice.name}")
                else:
                    if val_to_updt:
                        invoice.button_draft()
                        invoice.write(val_to_updt)
                        invoice.action_post()

    def _build_invoice_data(self, contract=False, due_date=False, ref=False, pay_mode_id=False):
        """
        It takes a list of invoice lines, a due date, a payment reference, and a payment mode, and returns a dictionary with
        the invoice lines, the due date, the payment reference, and the payment mode

        :param inv_lines: a list of dictionaries containing the invoice lines to be added to the invoice, defaults to False
        (optional)
        :param due_date: The date at which the invoice should be paid, defaults to False (optional)
        :param ref: The reference of the invoice, defaults to False (optional)
        :param pay_mode_id: The payment mode to be used for the invoice, defaults to False (optional)
        :return: A dictionary with the invoice_line_ids, date, payment_reference, and payment_mode_id.
        """
        # Ensure that the funciton receive one invoice
        self.ensure_one()
        # Build the dictionnary
        inv_val_dict = {}
        if contract:
            inv_val_dict["invoice_line_ids"] = self._build_invoice_lines_from_contract(contract)
        if due_date:
            inv_val_dict["date"] = due_date
        if ref:
            inv_val_dict["payment_reference"] = ref
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
        # Line to delete in the invoice
        # If the invoice has different product than the contract we should delete the line
        diff_product_invoices = [p for p in line_ids.mapped("product_id").ids if
                                 p not in contract.contract_line_ids.mapped("product_id").ids]
        if diff_product_invoices:
            for diff_product_inv in diff_product_invoices:
                res.append((2, line_ids.filtered(lambda l: l.product_id.id == diff_product_inv).id, 0))
        # Line to create in the invoice
        # If the contract has different product than the invoice we should create the line
        diff_product_contract = [p for p in contract.contract_line_ids.mapped("product_id").ids if
                                 p not in line_ids.mapped("product_id").ids]
        if diff_product_contract:
            for diff_product_contr in diff_product_contract:
                contract_line = contract.contract_line_ids.filtered(lambda l: l.product_id.id == diff_product_contr)
                if contract_line:
                    res.append((0, 0,
                                {
                                    "price_unit": contract_line.amount,
                                    "product_id": contract_line.product_id.id,
                                    'name': contract_line.product_id.name,
                                    'quantity': contract_line.quantity,
                                    'contract_id': contract_line.contract_id.id,
                                    'account_id': contract_line.product_id.with_company(
                                        contract_line.contract_id.company_id.id).property_account_income_id.id or False
                                }
                                ))
        # Line to modify in the invoice
        line_ids.filtered(lambda l: l.product_id.id not in diff_product_contract
                                    and l.product_id.id not in diff_product_invoices)
        for line_id in line_ids:
            cl = contract.mapped("contract_line_ids").filtered(lambda l: l.product_id == line_id.product_id)
            if cl:
                res.append((1, line_id.id,
                            {
                                "price_unit": cl.amount,
                                "quantity": cl.quantity
                            }
                            )
                           )
        return res
