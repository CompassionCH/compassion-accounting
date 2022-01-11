##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import fields, models, api, _
from odoo.exceptions import UserError
from datetime import date


class AccountInvoice(models.Model):
    _name = 'account.invoice'
    _inherit = 'account.invoice'

    recurring_invoicer_id = fields.Many2one(
        'recurring.invoicer', 'Invoicer', readonly=False)

    @api.multi
    def action_invoice_paid(self):
        """ Call invoice_paid method on related contracts. """
        res = super().action_invoice_paid()
        for invoice in self:
            contracts = invoice.mapped('invoice_line_ids.contract_id')
            contracts.invoice_paid(invoice)
        return res

    @api.multi
    def action_invoice_re_open(self):
        """ Call invoice_unpaid method on related contract. """
        res = super().action_invoice_re_open()
        for invoice in self:
            contracts = invoice.mapped('invoice_line_ids.contract_id')
            contracts.invoice_unpaid(invoice)
        return res

    @api.multi
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
        cancel_invoices.action_invoice_draft()
        cancel_invoices.action_invoice_open()
        today = date.today()
        for partner_id in self.mapped('partner_id.id'):
            invoices = self.filtered(lambda i: i.partner_id.id == partner_id)
            past_invoices = invoices.filtered(
                lambda i: i.date_invoice <= today)
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
                    lines = past_invoices.mapped('move_id.line_ids').filtered("debit")
                    (lines + payment).reconcile()
                    is_past_reconciled = True
                elif not is_future_reconciled and payment.credit == future_amount:
                    lines = future_invoices.mapped('move_id.line_ids').filtered("debit")
                    (lines + payment).reconcile()
                    is_future_reconciled = True

            # If no matching payment found, we will group or split.
            if not is_past_reconciled:
                past_invoices._group_or_split_reconcile()
            if not is_future_reconciled:
                future_invoices._group_or_split_reconcile()

        return True

    @api.multi
    def _group_or_split_reconcile(self):
        """
        Find payments to reconcile given invoices and perform reconciliation.
        :return: True
        """
        partner = self.mapped('partner_id')
        partner.ensure_one()
        reconcile_amount = sum(self.mapped('amount_total'))
        move_lines = self.mapped('move_id.line_ids').filtered('debit')
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
            return (payment_greater_than_reconcile | move_lines)\
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
                    ret = find_sum(numbers[i+1:], target,
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
                        return (open_payments[:index + 1] | move_lines)\
                            .split_payment_and_reconcile()
                    payment_amount += payment_line.credit
                return (open_payments | move_lines).reconcile()


class AccountInvoiceLine(models.Model):
    _name = 'account.invoice.line'
    _inherit = 'account.invoice.line'

    contract_id = fields.Many2one(
        'recurring.contract', 'Source contract', index=True, readonly=False)

    due_date = fields.Date(
        related='invoice_id.date_due',
        readonly=True, store=True)

    state = fields.Selection(
        related='invoice_id.state',
        readonly=True, store=True)

    @api.multi
    def filter_for_contract_rewind(self, filter_state):
        """
        Returns a subset of invoice lines that should be used to find after which one
        we will set the next_invoice_date of a contract.
        :param filter_state: filter invoice lines that have the desired state
        :return: account.invoice.line recordset
        """
        company = self.mapped("contract_id.company_id")
        lock_date = company.period_lock_date
        return self.filtered(
            lambda l: l.state == filter_state and
            (not lock_date or (l.due_date and l.due_date > lock_date))
        )

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
