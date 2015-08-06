# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from datetime import datetime
from dateutil.relativedelta import relativedelta

from openerp import api, exceptions, fields, models, netsvc, _
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF
import openerp.addons.decimal_precision as dp


class recurring_contract_line(models.Model):
    """ Each product sold through a contract """

    _name = "recurring.contract.line"
    _description = "A contract line"

    def name_get(self, ids):
        if not ids:
            return []
        res = [(cl.id, cl.product_id.name_template) for cl in self.browse(ids)]
        return res

    contract_id = fields.Many2one(
        'recurring.contract', 'Contract', required=True,
        ondelete='cascade', readonly=True)
    product_id = fields.Many2one('product.product', 'Product',
                                 required=True)
    amount = fields.Float('Price', required=True)
    quantity = fields.Integer(default=1, required=True)
    subtotal = fields.Float(compute='_compute_subtotal', store=True,
                            digits_compute=dp.get_precision('Account'))

    @api.depends('amount', 'quantity')
    @api.one
    def _compute_subtotal(self):
        self.subtotal = self.amount * self.quantity

    @api.onchange('product_id')
    def on_change_product_id(self):
        if not self.product_id:
            self.amount = 0.0
        else:
            self.amount = self.product_id.list_price


class recurring_contract(models.Model):
    """ A contract to perform recurring invoicing to a partner """

    _name = "recurring.contract"
    _description = "Contract for recurring invoicing"
    _inherit = ['mail.thread']
    _rec_name = 'reference'

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################

    reference = fields.Char(
        default="/", required=True, readonly=True,
        states={'draft': [('readonly', False)]})
    start_date = fields.Date(
        default=datetime.today().strftime(DF), required=True, readonly=True,
        states={'draft': [('readonly', False)]}, track_visibility="onchange")
    end_date = fields.Date(
        readonly=False, states={'terminated': [('readonly', True)]},
        track_visibility="onchange")
    next_invoice_date = fields.Date(
        readonly=False, states={'draft': [('readonly', False)]},
        track_visibility="onchange")
    last_paid_invoice_date = fields.Date(
        compute='_get_last_paid_invoice')
    partner_id = fields.Many2one(
        'res.partner', 'Partner', required=True, readonly=True,
        states={'draft': [('readonly', False)]}, ondelete='restrict')
    group_id = fields.Many2one(
        'recurring.contract.group', 'Payment Options',
        required=True, ondelete='cascade', track_visibility="onchange")
    invoice_line_ids = fields.One2many(
        'account.invoice.line', 'contract_id',
        'Related invoice lines', readonly=True)
    contract_line_ids = fields.One2many(
        'recurring.contract.line', 'contract_id',
        'Contract lines', track_visibility="onchange", copy=True)
    state = fields.Selection([
        ('draft', _('Draft')),
        ('active', _('Active')),
        ('terminated', _('Terminated'))], 'Status', default='draft',
        select=True, readonly=True, track_visibility='onchange',
        help=_(" * The 'Draft' status is used when a user is encoding a "
               "new and unconfirmed Contract.\n"
               "* The 'Active' status is used when the contract is "
               "confirmed and until it's terminated.\n"
               "* The 'Terminated' status is used when a contract is no "
               "longer active."))
    total_amount = fields.Float(
        'Total', compute='_get_total_amount',
        digits_compute=dp.get_precision('Account'),
        track_visibility="onchange", store=True)
    payment_term_id = fields.Many2one(
        'account.payment.term', string='Payment Term',
        related='group_id.payment_term_id', readonly=True, store=True)

    ##########################################################################
    #                             FIELDS METHODS                             #
    ##########################################################################

    @api.depends('contract_line_ids', 'contract_line_ids.amount',
                 'contract_line_ids.quantity')
    def _get_total_amount(self):
        self.total_amount = sum([line.subtotal for line in
                                 self.contract_line_ids])

    @api.one
    def _get_last_paid_invoice(self):
        self.last_paid_invoice_date = max(
            [invl.invoice_id.date_invoice for invl in self.invoice_line_ids
             if invl.state == 'paid'] or [False])

    @api.constrains('reference')
    @api.one
    def _check_unique_reference(self):
        chk_list_contracts = self.search([]) - self
        ref_lst = [contract.reference for contract in chk_list_contracts
                   if contract.reference]
        if self.reference in ref_lst:
            raise exceptions.ValidationError(
                _('Error: Reference should be unique'))
        return True

    ##########################################################################
    #                              ORM METHODS                               #
    ##########################################################################

    @api.model
    def create(self, vals):
        """ Add a sequence generated ref if none is given """
        if vals.get('reference', '/') == '/':
            vals['reference'] = self.env['ir.sequence'].next_by_code(
                'recurring.contract.ref')

        return super(recurring_contract, self).create(vals)

    @api.multi
    def write(self, vals):
        """ Perform various checks when a contract is modified. """
        if 'next_invoice_date' in vals:
            self._on_change_next_invoice_date(vals['next_invoice_date'])

        res = super(recurring_contract, self).write(vals)

        if 'contract_line_ids' in vals:
            self._on_contract_lines_changed()

        return res

    @api.one
    def copy(self, default=None):
        default = default or dict()
        today = datetime.today()
        old_contract = self
        next_invoice_date = datetime.strptime(old_contract.next_invoice_date,
                                              DF)
        next_invoice_date = next_invoice_date.replace(month=today.month)
        default.update({
            'state': 'draft',
            'reference': '/',
            'start_date': today.strftime(DF),
            'end_date': False,
            'next_invoice_date': next_invoice_date.strftime(DF),
            'invoice_line_ids': False,
        })
        return super(recurring_contract, self).copy(default)

    @api.one
    def unlink(self):
        if self.state not in ('draft', 'terminated'):
            raise exceptions.Warning(
                'UserError',
                _('You cannot delete a contract that is still active. '
                  'Terminate it first.'))
        else:
            super(recurring_contract, self).unlink()

        return True

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################

    def clean_invoices(self, since_date=None, to_date=None, keep_lines=None):
        """ This method deletes invoices lines generated for a given contract
            having a due date >= current month. If the invoice_line was the
            only line in the invoice, we cancel the invoice. In the other
            case, we have to revalidate the invoice to update the move lines.
        """
        invl_search = [('contract_id', 'in', self.ids),
                       ('state', 'not in', ('paid', 'cancel'))]
        if since_date:
            invl_search.append(('due_date', '>=', since_date))
        if to_date:
            invl_search.append(('due_date', '<=', to_date))

        # Find all unpaid invoice lines after the given date
        inv_lines = self.env['account.invoice.line'].search(invl_search)

        inv_ids = set()
        empty_inv_ids = set()
        to_remove_ids = []   # Invoice lines that will be moved or removed
        for inv_line in inv_lines:
            invoice = inv_line.invoice_id
            inv_ids.add(invoice.id)
            # Check if invoice is empty after removing the invoice_lines
            # of the given contract
            if invoice.id not in empty_inv_ids:
                remaining_lines_ids = [
                    invl.id for invl in invoice.invoice_line if
                    not invl.contract_id or
                    invl.contract_id and invl.contract_id.id not in self.ids]
                if remaining_lines_ids:
                    # We can move or remove the line
                    to_remove_ids.append(inv_line.id)
                else:
                    # The invoice would be empty if we remove the line
                    empty_inv_ids.add(invoice.id)

        if keep_lines:
            self._move_cancel_lines(to_remove_ids, keep_lines)
        else:
            to_remove_recset = self.env['account.invoice.line'].browse(
                to_remove_ids)
            to_remove_recset.unlink()

        # Invoices to set back in open state
        renew_inv_ids = list(inv_ids - empty_inv_ids)

        self._cancel_confirm_invoices(list(inv_ids), renew_inv_ids,
                                      keep_lines)

        return inv_ids

    def rewind_next_invoice_date(self):
        """ Rewinds the next invoice date of contract after the last
        generated invoice. No open invoices exist after that date. """
        gen_states = self.env['recurring.contract.group']._get_gen_states()
        for contract in self:
            if contract.state in gen_states:
                last_invoice_date = max([
                    datetime.strptime(line.invoice_id.date_invoice, DF) for
                    line in contract.invoice_line_ids
                    if line.state in ('open', 'paid')] or [False])
                if last_invoice_date:
                    # Call super for allowing rewind.
                    super(recurring_contract, self).write({
                        'next_invoice_date':
                        last_invoice_date.strftime(DF)})
                    contract.update_next_invoice_date()
                else:
                    # No open/paid invoices, look for cancelled ones
                    next_invoice_date = min([
                        datetime.strptime(line.invoice_id.date_invoice, DF)
                        for line in contract.invoice_line_ids
                        if line.state == 'cancel'] or [False])
                    if next_invoice_date:
                        super(recurring_contract, self).write({
                            'next_invoice_date':
                            next_invoice_date.strftime(DF)})

        return True

    def update_next_invoice_date(self):
        """ Recompute and set next_invoice date. """
        next_date = self._compute_next_invoice_date()
        self.write({'next_invoice_date': next_date})
        return True

    ##########################################################################
    #                             VIEW CALLBACKS                             #
    ##########################################################################

    @api.onchange('start_date')
    def on_change_start_date(self):
        """ We automatically update next_invoice_date on start_date change """
        if self.start_date:
            self.next_invoice_date = self.start_date

    @api.onchange('partner_id')
    def on_change_partner_id(self):
        """ On partner change, we update the group_id. If partner has
        only 1 group, we take it. Else, we take nothing.
        """
        group_ids = self.env['recurring.contract.group'].search(
            [('partner_id', '=', self.partner_id.id)])

        self.group_id = None
        if len(group_ids) == 1:
            self.group_id = group_ids[0]

    ##########################################################################
    #                            WORKFLOW METHODS                            #
    ##########################################################################

    @api.multi
    def button_generate_invoices(self):
        return self.group_id.button_generate_invoices()

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
            contracts.contract_terminated()

        return True

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################

    @api.one
    def _on_contract_lines_changed(self):
        """Update related invoices to reflect the changes to the contract.
        """
        # Find all unpaid invoice lines after the given date
        since_date = datetime.today().replace(day=1).strftime(DF)
        inv_lines = self.env['account.invoice.line'].search(
            [('contract_id', '=', self.id),
             ('due_date', '>=', since_date),
             ('state', 'not in', ('paid', 'cancel'))])

        invoices = inv_lines.mapped('invoice_id')
        invoices.action_cancel()
        invoices.action_cancel_draft()
        self._update_invoice_lines(invoices)
        wf_service = netsvc.LocalService('workflow')
        for invoice_id in invoices.ids:
            wf_service.trg_validate(self.env.user.id, 'account.invoice',
                                    invoice_id, 'invoice_open', self.env.cr)

    @api.one
    def _move_cancel_lines(self, invoice_line_ids, message=None):
        """ Method that takes out given invoice_lines from their invoice
        and put them in a cancelled copy of that invoice.
        Warning : this method does not recompute totals of original invoices,
                  and does not update related move lines.
        """
        invoice_obj = self.env['account.invoice']
        invoice_line_obj = self.env['account.invoice.line']
        invoices_copy = dict()
        for invoice_line in invoice_line_obj.browse(invoice_line_ids):
            invoice = invoice_line.invoice_id
            copy_invoice_id = invoices_copy.get(invoice.id)
            if not copy_invoice_id:
                invoice_obj.copy(invoice.id, {
                    'date_invoice': invoice.date_invoice})
                copy_invoice_id = invoice_obj.search(
                    [('partner_id', '=', invoice.partner_id.id),
                     ('state', '=', 'draft'), ('id', '!=', invoice.id),
                     ('date_invoice', '=', invoice.date_invoice)])[0]
                # Empty the new invoice
                cancel_lines = invoice_line_obj.search([
                    ('invoice_id', '=', copy_invoice_id)])
                invoice_line_obj.unlink(cancel_lines)
                invoices_copy[invoice.id] = copy_invoice_id

            # Move the line in the invoice copy
            invoice_line.write({'invoice_id': copy_invoice_id})

        # Compute and cancel invoice copies
        cancel_ids = invoice_obj.browse(invoices_copy.values())
        if cancel_ids:
            cancel_ids.button_compute(set_total=True)
            wf_service = netsvc.LocalService('workflow')
            for cancel_id in cancel_ids:
                wf_service.trg_validate(
                    self.env.user.id, 'account.invoice', cancel_id,
                    'invoice_cancel', self.env.cr)

            cancel_ids.message_post(
                message, _("Invoice Cancelled"), 'comment')

        return True

    @api.one
    def _cancel_confirm_invoices(self, cancel_ids, confirm_ids,
                                 keep_lines=None):
        """ Cancels given invoices and validate again given invoices.
            confirm_ids must be a subset of cancel_ids ! """
        inv_obj = self.env['account.invoice']
        wf_service = netsvc.LocalService('workflow')
        invoice_confirm = inv_obj.browse(confirm_ids)

        for invoice_id in cancel_ids:
            wf_service.trg_validate(self.env.user.id, 'account.invoice',
                                    invoice_id, 'invoice_cancel', self.env.cr)
        invoice_confirm.action_cancel_draft()
        for invoice_id in confirm_ids:
            wf_service.trg_validate(self.env.user.id, 'account.invoice',
                                    invoice_id, 'invoice_open', self.env.cr)

    def _compute_next_invoice_date(self):
        """ Compute next_invoice_date for a single contract. """
        next_date = datetime.strptime(self.next_invoice_date, DF)
        rec_unit = self.group_id.recurring_unit
        rec_value = self.group_id.recurring_value
        if rec_unit == 'day':
            next_date = next_date + relativedelta(days=+rec_value)
        elif rec_unit == 'week':
            next_date = next_date + relativedelta(weeks=+rec_value)
        elif rec_unit == 'month':
            next_date = next_date + relativedelta(months=+rec_value)
        else:
            next_date = next_date + relativedelta(years=+rec_value)

        return next_date.strftime(DF)

    @api.one
    def _update_invoice_lines(self, invoices):
        """Update invoice lines generated by a contract, when the contract
        was modified and corresponding invoices were cancelled.

        Parameters:
            - invoice_ids (list): ids of draft invoices to be
                                  updated and validated
        """
        group_obj = self.env['recurring.contract.group'].with_context(
            no_next_date_update=True)
        # Update payment term
        invoices.write({
            'payment_term': self.group_id.payment_term_id and
            self.group_id.payment_term_id.id or False})

        for invoice in invoices:
            # Generate new invoice_lines
            old_lines = invoice.invoice_line.filtered(
                lambda line: line.contract_id.id == self.id)
            old_lines.unlink()
            group_obj._generate_invoice_lines(self, invoice)

    @api.one
    def _on_change_next_invoice_date(self, new_invoice_date):
        new_invoice_date = datetime.strptime(new_invoice_date, DF)
        if self.next_invoice_date:
            next_invoice_date = datetime.strptime(self.next_invoice_date, DF)
            if next_invoice_date > new_invoice_date:
                raise exceptions.Warning(
                    'Error', _('You cannot rewind the next invoice date.'))
        return True
