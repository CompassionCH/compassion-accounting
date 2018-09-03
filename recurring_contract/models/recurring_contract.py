# -*- coding: utf-8 -*-
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

import odoo.addons.decimal_precision as dp
from dateutil.relativedelta import relativedelta
from odoo.addons.queue_job.job import job, related_action

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF

_logger = logging.getLogger(__name__)


class ContractLine(models.Model):
    """ Each product sold through a contract """

    _name = "recurring.contract.line"
    _description = "A contract line"

    @api.multi
    def name_get(self):
        res = [(cl.id, cl.product_id.name) for cl in self]
        return res

    contract_id = fields.Many2one(
        'recurring.contract', 'Contract', required=True,
        ondelete='cascade', readonly=True)
    product_id = fields.Many2one('product.product', 'Product',
                                 required=True)
    amount = fields.Float('Price', required=True)
    quantity = fields.Integer(default=1, required=True)
    subtotal = fields.Float(compute='_compute_subtotal', store=True,
                            digits=dp.get_precision('Account'))

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


class RecurringContract(models.Model):
    """ A contract to perform recurring invoicing to a partner """

    _name = "recurring.contract"
    _description = "Contract for recurring invoicing"
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _rec_name = 'reference'

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################

    reference = fields.Char(
        default="/", required=True, readonly=True,
        states={'draft': [('readonly', False)]}, copy=False)
    start_date = fields.Date(
        readonly=True, states={'draft': [('readonly', False)]},
        copy=False, track_visibility="onchange")
    end_date = fields.Datetime(
        readonly=False, states={'terminated': [('readonly', True)]},
        track_visibility="onchange", copy=False)
    next_invoice_date = fields.Date(
        readonly=False, states={'draft': [('readonly', False)]},
        track_visibility="onchange")
    last_paid_invoice_date = fields.Date(
        compute='_compute_last_paid_invoice')
    partner_id = fields.Many2one(
        'res.partner', 'Partner', required=True, readonly=True,
        states={'draft': [('readonly', False)]}, ondelete='restrict')
    group_id = fields.Many2one(
        'recurring.contract.group', 'Payment Options',
        required=True, ondelete='cascade', track_visibility="onchange")
    invoice_line_ids = fields.One2many(
        'account.invoice.line', 'contract_id',
        'Related invoice lines', readonly=True, copy=False)
    contract_line_ids = fields.One2many(
        'recurring.contract.line', 'contract_id',
        'Contract lines', track_visibility="onchange", copy=True)
    state = fields.Selection(
        '_get_states', default='draft', readonly=True,
        track_visibility='onchange', copy=False)
    total_amount = fields.Float(
        'Total', compute='_compute_total_amount',
        digits=dp.get_precision('Account'),
        track_visibility="onchange", store=True)
    payment_mode_id = fields.Many2one(
        'account.payment.mode', string='Payment mode',
        related='group_id.payment_mode_id', readonly=True, store=True)
    nb_invoices = fields.Integer(compute='_compute_invoices')

    _sql_constraints = [
        ('unique_ref', "unique(reference)", "Reference must be unique!")
    ]

    ##########################################################################
    #                             FIELDS METHODS                             #
    ##########################################################################
    @api.model
    def _get_states(self):
        return [
            ('draft', _('Draft')),
            ('active', _('Active')),
            ('terminated', _('Terminated'))
        ]

    @api.depends('contract_line_ids', 'contract_line_ids.amount',
                 'contract_line_ids.quantity')
    def _compute_total_amount(self):
        for contract in self:
            contract.total_amount = sum([
                line.subtotal for line in contract.contract_line_ids
            ])

    def _compute_last_paid_invoice(self):
        for contract in self:
            contract.last_paid_invoice_date = max(
                [invl.invoice_id.date_invoice for invl in
                 contract.invoice_line_ids if invl.state == 'paid'] or [False])

    def _compute_invoices(self):
        for contract in self:
            contract.nb_invoices = len(
                contract.mapped('invoice_line_ids.invoice_id').filtered(
                    lambda i: i.state not in ('cancel', 'draft')
                ))

    ##########################################################################
    #                              ORM METHODS                               #
    ##########################################################################

    @api.model
    def create(self, vals):
        """ Add a sequence generated ref if none is given """
        if vals.get('reference', '/') == '/':
            vals['reference'] = self.env['ir.sequence'].next_by_code(
                'recurring.contract.ref')

        return super(RecurringContract, self).create(vals)

    @api.multi
    def write(self, vals):
        """ Perform various checks when a contract is modified. """
        if 'next_invoice_date' in vals:
            self._on_change_next_invoice_date(vals['next_invoice_date'])

        res = super(RecurringContract, self).write(vals)

        if 'contract_line_ids' in vals:
            self._on_contract_lines_changed()

        return res

    @api.multi
    def copy(self, default=None):
        for contract in self:
            default = default or dict()
            if contract.last_paid_invoice_date:
                next_invoice_date = datetime.strptime(
                    contract.last_paid_invoice_date,
                    DF) + relativedelta(months=1)
            else:
                today = datetime.today()
                next_invoice_date = datetime.strptime(
                    contract.next_invoice_date, DF)
                next_invoice_date = next_invoice_date.replace(
                    month=today.month, year=today.year)
            default['next_invoice_date'] = next_invoice_date.strftime(DF)
        return super(RecurringContract, self).copy(default)

    @api.multi
    def unlink(self):
        for contract in self:
            if contract.state == 'active':
                raise UserError(
                    _('You cannot delete a contract that is still active. '
                      'Terminate it first.'))
            else:
                super(RecurringContract, contract).unlink()

        return True

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################
    @api.multi
    def clean_invoices(self, since_date=None, to_date=None, keep_lines=None):
        """ By default, launch asynchronous job to perform the task.
            Context value async_mode set to False can force to perform
            the task immediately.
        """
        if self.env.context.get('async_mode', True):
            self.with_delay()._clean_invoices(since_date, to_date, keep_lines)
        else:
            self._clean_invoices(since_date, to_date, keep_lines)

    def rewind_next_invoice_date(self):
        """ Rewinds the next invoice date of contract after the last
        generated invoice. No open invoices exist after that date. """
        gen_states = self.env['recurring.contract.group']._get_gen_states()
        for contract in self.with_context(allow_rewind=True):
            if contract.state in gen_states:
                last_invoice_date = max([
                    datetime.strptime(line.invoice_id.date_invoice, DF) for
                    line in contract.invoice_line_ids
                    if line.state in ('open', 'paid')] or [False])
                if last_invoice_date:
                    contract.write({
                        'next_invoice_date': last_invoice_date.strftime(DF)})
                    contract.update_next_invoice_date()
                else:
                    # No open/paid invoices, look for cancelled ones
                    next_invoice_date = min([
                        datetime.strptime(line.invoice_id.date_invoice, DF)
                        for line in contract.invoice_line_ids
                        if line.state == 'cancel'] or [False])
                    if next_invoice_date:
                        contract.write({
                            'next_invoice_date':
                            next_invoice_date.strftime(DF)})

        return True

    def update_next_invoice_date(self):
        """ Recompute and set next_invoice date. """
        for contract in self:
            next_date = contract._compute_next_invoice_date()
            contract.write({'next_invoice_date': next_date})
        return True

    @api.multi
    def get_inv_lines_data(self):
        """ Setup a dict with data passed to invoice_line.create.
        If any custom data is wanted in invoice line from contract,
        just inherit this method.
        :return: list of dictionaries
        """
        res = list()
        default_account = self.env['account.invoice.line']._default_account()
        for contract_line in self.mapped('contract_line_ids'):
            product = contract_line.product_id
            inv_line_data = {
                'name': product.name,
                'price_unit': contract_line.amount,
                'quantity': contract_line.quantity,
                'product_id': product.id,
                'contract_id': contract_line.contract_id.id,
                'account_id': product.property_account_income_id.id or
                default_account
            }
            res.append(inv_line_data)
        return res

    ##########################################################################
    #                             VIEW CALLBACKS                             #
    ##########################################################################
    @api.onchange('partner_id')
    def on_change_partner_id(self):
        """ On partner change, we update the group_id. If partner has
        only 1 group, we take it. Else, we take nothing.
        """
        group_ids = self.env['recurring.contract.group'].search(
            [('partner_id', '=', self.partner_id.id)])
        if len(group_ids) == 1:
            self.group_id = group_ids[0]
        else:
            self.group_id = False

    @api.multi
    def button_generate_invoices(self):
        """ Immediately generate invoices of the contract group. """
        return self.mapped('group_id').with_context(
            async_mode=False).generate_invoices()

    @api.multi
    def open_invoices(self):
        self.ensure_one()
        invoice_ids = self.mapped('invoice_line_ids.invoice_id').ids
        return {
            'name': _('Contract invoices'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'views': [
                (self.env.ref('account.invoice_tree').id, 'tree'),
                (self.env.ref('account.invoice_form').id, 'form'),
            ],
            'res_model': 'account.invoice',
            'domain': [('id', 'in', invoice_ids)],
            'context': self.with_context(
                form_view_ref='account.invoice_form',
                search_default_invoices=True
            ).env.context,
            'target': 'current',
        }

    ##########################################################################
    #                            WORKFLOW METHODS                            #
    ##########################################################################
    @api.multi
    def contract_draft(self):
        self.write({'state': 'draft'})
        return True

    @api.multi
    def contract_active(self):
        self.write({'state': 'active'})
        return True

    @api.multi
    def contract_terminated(self):
        today = datetime.today().strftime(DF)
        self.write({'state': 'terminated', 'end_date': today})
        self.clean_invoices()
        return True

    @api.model
    def end_date_reached(self):
        today = datetime.today().strftime(DF)
        contracts = self.search([('state', '=', 'active'),
                                 ('end_date', '<=', today)])

        if contracts:
            contracts.signal_workflow('contract_terminated')

        return True

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################
    @api.multi
    @job(default_channel='root.recurring_invoicer')
    @related_action(action='related_action_contract')
    def _clean_invoices(self, since_date=None, to_date=None, keep_lines=None):
        """ This method deletes invoices lines generated for a given contract
            having a due date >= current month. If the invoice_line was the
            only line in the invoice, we cancel the invoice. In the other
            case, we have to revalidate the invoice to update the move lines.
        """
        _logger.info("clean invoices called.")
        inv_lines = self._get_invoice_lines_to_clean(since_date, to_date)
        invoices = inv_lines.mapped('invoice_id')
        empty_invoices = self.env['account.invoice']
        to_remove_invl = self.env['account.invoice.line']

        for inv_line in inv_lines:
            invoice = inv_line.invoice_id
            # Check if invoice is empty after removing the invoice_lines
            # of the given contract
            if invoice not in empty_invoices:
                remaining_lines = invoice.invoice_line_ids.filtered(
                    lambda l: not l.contract_id or l.contract_id not in self)
                if remaining_lines:
                    # We can move or remove the line
                    to_remove_invl |= inv_line
                else:
                    # The invoice would be empty if we remove the line
                    empty_invoices |= invoice

        if keep_lines:
            self._move_cancel_lines(to_remove_invl, keep_lines)
        else:
            invoices.action_invoice_cancel()
            invoices.action_invoice_draft()
            invoices.env.invalidate_all()
            to_remove_invl.unlink()

        # Refresh cache before calling workflows
        self.env.invalidate_all()
        # Invoices to set back in open state
        renew_invs = invoices - empty_invoices
        self._cancel_confirm_invoices(invoices, renew_invs, keep_lines)

        _logger.info(str(len(invoices)) + " invoices cleaned.")
        return invoices

    def _on_contract_lines_changed(self):
        """Update related invoices to reflect the changes to the contract.
        """
        inv_lines = self.env['account.invoice.line'].search(
            [('contract_id', 'in', self.ids),
             ('state', 'not in', ('paid', 'cancel'))])

        invoices = inv_lines.mapped('invoice_id')
        invoices.action_invoice_cancel()
        invoices.action_invoice_draft()
        invoices.env.invalidate_all()
        self._update_invoice_lines(invoices)
        invoices.action_invoice_open()

    @api.model
    def _move_cancel_lines(self, invoice_lines, message=None):
        """ Method that takes out given invoice_lines from their invoice
        and put them in a cancelled copy of that invoice.
        Warning : this method does not recompute totals of original invoices,
                  and does not update related move lines.
        """
        invoice_obj = self.env['account.invoice']
        invoices_copy = dict()
        for invoice_line in invoice_lines:
            invoice = invoice_line.invoice_id
            copy_invoice_id = invoices_copy.get(invoice.id)
            if not copy_invoice_id:
                copy_invoice_id = invoice.copy({
                    'date_invoice': invoice.date_invoice,
                    'date_due': invoice.date_invoice}).id
                # Empty the new invoice
                cancel_lines = self.env['account.invoice.line'].search([
                    ('invoice_id', '=', copy_invoice_id)])
                cancel_lines.unlink()
                invoices_copy[invoice.id] = copy_invoice_id

            # Move the line in the invoice copy
            invoice_line.write({'invoice_id': copy_invoice_id})

        # Compute and cancel invoice copies
        cancel_invoices = invoice_obj.browse(invoices_copy.values())
        cancel_invoices.action_invoice_cancel()
        for ci in cancel_invoices:
            ci.message_post(message, _("Invoice Cancelled"), 'comment')

        return True

    @api.model
    def _cancel_confirm_invoices(self, invoice_cancel, invoice_confirm,
                                 keep_lines=None):
        """ Cancels given invoices and validate again given invoices.
            confirm_ids must be a subset of cancel_ids ! """
        _logger.info("clean invoices : \n\t"
                     "invoices to cancel : " + str(invoice_cancel.ids) +
                     "\n\tinvoices to confirm : " + str(invoice_confirm.ids))
        invoice_cancel.action_invoice_cancel()
        invoice_confirm.action_invoice_draft()
        invoice_confirm.env.invalidate_all()
        invoice_confirm.action_invoice_open()

    def _compute_next_invoice_date(self):
        """ Compute next_invoice_date for a single contract. """
        next_date = datetime.strptime(self.next_invoice_date, DF)
        next_date += self.group_id.get_relative_delta()
        return next_date.strftime(DF)

    def _update_invoice_lines(self, invoices):
        """Update invoice lines generated by a contract, when the contract
        was modified and corresponding invoices were cancelled.

        Parameters:
            - invoice_ids (list): ids of draft invoices to be
                                  updated and validated
        """
        for contract in self:
            # Update payment term
            invoices.write({
                'payment_mode_id': contract.payment_mode_id.id
            })

            for invoice in invoices:
                # Generate new invoice_lines
                old_lines = invoice.invoice_line_ids.filtered(
                    lambda line: line.contract_id.id == contract.id)
                old_lines.unlink()
                journal = invoice.journal_id
                invl = [(0, 0, l) for l in
                        contract.with_context(
                            journal_id=journal.id).get_inv_lines_data() if l]
                invoice.write({'invoice_line_ids': invl})

    def _on_change_next_invoice_date(self, new_invoice_date):
        for contract in self:
            new_invoice_date = datetime.strptime(new_invoice_date, DF)
            if contract.next_invoice_date:
                next_invoice_date = datetime.strptime(
                    contract.next_invoice_date, DF)
                if next_invoice_date > new_invoice_date and not \
                        self.env.context.get('allow_rewind'):
                    raise UserError(
                        _('You cannot rewind the next invoice date.'))
        return True

    def _get_invoice_lines_to_clean(self, since_date, to_date):
        """ Find all unpaid invoice lines in the given period. """
        invl_search = [('contract_id', 'in', self.ids),
                       ('state', 'not in', ('paid', 'cancel'))]
        if since_date:
            invl_search.append(('due_date', '>=', since_date))
        if to_date:
            invl_search.append(('due_date', '<=', to_date))

        return self.env['account.invoice.line'].search(invl_search)
