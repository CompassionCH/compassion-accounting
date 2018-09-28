# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>, Steve Ferry, Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################

import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.tools import config

from odoo.addons.queue_job.job import job, related_action

logger = logging.getLogger(__name__)
test_mode = config.get('test_enable')


class ContractGroup(models.Model):
    _name = 'recurring.contract.group'
    _description = 'A group of contracts'
    _inherit = 'mail.thread'
    _rec_name = 'ref'

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################
    advance_billing_months = fields.Integer(
        'Advance billing months',
        help='Advance billing allows you to generate invoices in '
             'advance. For example, you can generate the invoices '
             'for each month of the year and send them to the '
             'customer in january.', default=1, ondelete='no action')
    payment_mode_id = fields.Many2one(
        'account.payment.mode', 'Payment mode',
        domain=[('payment_type', '=', 'inbound')],
        track_visibility='onchange'
    )
    # Todo remove after v9 migration
    payment_term_id = fields.Many2one('account.payment.term',
                                      'Payment Term',
                                      track_visibility="onchange")
    next_invoice_date = fields.Date(
        compute='_compute_next_invoice_date',
        string='Next invoice date', store=True)
    last_paid_invoice_date = fields.Date(
        compute='_compute_last_paid_invoice',
        string='Last paid invoice date')

    change_method = fields.Selection(
        '_get_change_methods', default='do_nothing')
    partner_id = fields.Many2one(
        'res.partner', 'Partner', required=True,
        ondelete='cascade', track_visibility="onchange")
    ref = fields.Char('Reference', default="/")
    recurring_unit = fields.Selection([
        ('day', _('Day(s)')),
        ('week', _('Week(s)')),
        ('month', _('Month(s)')),
        ('year', _('Year(s)'))], 'Reccurency',
        default='month', required=True)
    recurring_value = fields.Integer(
        'Generate every', default=1, required=True)
    contract_ids = fields.One2many(
        'recurring.contract', 'group_id', 'Contracts', readonly=True)

    ##########################################################################
    #                             FIELDS METHODS                             #
    ##########################################################################

    @api.depends('contract_ids.next_invoice_date', 'contract_ids.state')
    def _compute_next_invoice_date(self):
        for group in self:
            next_inv_date = min(
                [c.next_invoice_date for c in group.contract_ids
                 if c.state in self._get_gen_states()] or [False])
            group.next_invoice_date = next_inv_date

    def _compute_last_paid_invoice(self):
        for group in self:
            group.last_paid_invoice_date = max(
                [c.last_paid_invoice_date for c in group.contract_ids] or
                [False])

    ##########################################################################
    #                              ORM METHODS                               #
    ##########################################################################

    @api.multi
    def write(self, vals):
        """
            Perform various check at contract modifications
            - Advance billing increased or decrease
            - Recurring value or unit changes
            - Another change method was selected
        """
        res = True
        for group in self:
            # Check if group has an next_invoice_date
            if not group.next_invoice_date or 'next_invoice_date' in vals:
                res = super(ContractGroup, group).write(vals) and res
                continue

            # Get the method to apply changes
            change_method = vals.get('change_method', group.change_method)
            change_method = getattr(group, change_method)

            res = super(ContractGroup, group).write(vals) & res
            change_method()

        return res

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################
    @api.multi
    def clean_invoices(self):
        """ By default, launch asynchronous job to perform the task.
            Context value async_mode set to False can force to perform
            the task immediately.
        """
        if self.env.context.get('async_mode', True):
            self.with_delay()._clean_generate_invoices()
        else:
            self._clean_generate_invoices()
        return True

    def do_nothing(self):
        """ No changes before generation """
        pass

    @api.multi
    def generate_invoices(self, invoicer=None):
        """ By default, launch asynchronous job to perform the task.
            Context value async_mode set to False can force to perform
            the task immediately.
        """
        if invoicer is None:
            invoicer = self.env['recurring.invoicer'].create(
                {'source': self._name})
        if self.env.context.get('async_mode', True):
            # Prevent two generations at the same time
            jobs = self.env['queue.job'].search([
                ('channel', '=', 'root.recurring_invoicer'),
                ('state', '=', 'started')])
            delay = datetime.today()
            if jobs:
                delay += relativedelta(minutes=1)
            self.with_delay(eta=delay)._generate_invoices(invoicer)
        else:
            self._generate_invoices(invoicer)
        return invoicer

    @api.multi
    def get_relative_delta(self):
        """
        Get a relative delta given the recurring settings
        :return: datetime.relativedelta object
        """
        self.ensure_one()
        rec_unit = self.recurring_unit
        rec_value = self.recurring_value
        if rec_unit == 'day':
            r = relativedelta(days=+rec_value)
        elif rec_unit == 'week':
            r = relativedelta(weeks=+rec_value)
        elif rec_unit == 'month':
            r = relativedelta(months=+rec_value)
        else:
            r = relativedelta(years=+rec_value)
        return r

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################
    @api.multi
    @job(default_channel='root.recurring_invoicer')
    @related_action(action='related_action_invoicer')
    def _generate_invoices(self, invoicer=None):
        """ Checks all contracts and generate invoices if needed.
        Create an invoice per contract group per date.
        """
        logger.info("Invoice generation started.")
        if invoicer is None:
            invoicer = self.env['recurring.invoicer'].create(
                {'source': self._name})
        inv_obj = self.env['account.invoice']
        gen_states = self._get_gen_states()
        journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', 1)], limit=1)

        nb_groups = len(self)
        count = 1
        for contract_group in self.filtered('next_invoice_date'):
            # After a ContractGroup is done, we commit all writes in order to
            # avoid doing it again in case of an error or a timeout
            if not test_mode:
                self.env.cr.commit()    # pylint: disable=invalid-commit
            logger.info("Generating invoices for group {0}/{1}".format(
                count, nb_groups))
            month_delta = contract_group.advance_billing_months or 1
            limit_date = datetime.today() + relativedelta(
                months=+month_delta)
            current_date = fields.Datetime.from_string(
                contract_group.next_invoice_date)
            while current_date <= limit_date:
                contracts = contract_group.contract_ids.filtered(
                    lambda c: c.next_invoice_date and
                    fields.Datetime.from_string(
                        c.next_invoice_date) <= current_date and
                    c.state in gen_states and not (
                        c.end_date and c.end_date >= c.next_invoice_date)
                )
                if not contracts:
                    break
                try:
                    inv_data = contract_group._setup_inv_data(
                        journal, invoicer, contracts)
                    invoice = inv_obj.create(inv_data)
                    if invoice.invoice_line_ids:
                        invoice.action_invoice_open()
                    else:
                        invoice.unlink()
                    if not self.env.context.get('no_next_date_update'):
                        contracts.update_next_invoice_date()
                    current_date += contract_group.get_relative_delta()
                except:
                    self.env.cr.rollback()
                    self.env.invalidate_all()
                    logger.error(
                        'contract group {0} failed during invoice generation'.
                        format(contract_group.id),
                        exc_info=True)
                    break
            count += 1
        logger.info("Invoice generation successfully finished.")
        return invoicer

    @api.multi
    @job(default_channel='root.recurring_invoicer')
    def _clean_generate_invoices(self):
        """ Change method which cancels generated invoices and rewinds
        the next_invoice_date of contracts, so that new invoices can be
        generated taking into consideration the modifications of the
        contract group.
        """
        res = self.env['account.invoice']
        for group in self:
            since_date = datetime.today()
            if group.last_paid_invoice_date:
                last_paid_invoice_date = fields.Datetime.from_string(
                    group.last_paid_invoice_date)
                since_date = max(since_date, last_paid_invoice_date)
            res += group.contract_ids._clean_invoices(
                since_date=fields.Datetime.to_string(since_date))
            group.contract_ids.rewind_next_invoice_date()
        # Generate again invoices
        self._generate_invoices()
        return res

    @api.multi
    def _get_change_methods(self):
        """ Method for applying changes """
        return [
            ('do_nothing',
             'Nothing'),
            ('clean_invoices',
             'Clean invoices')
        ]

    def _get_gen_states(self):
        return ['active']

    def _setup_inv_data(self, journal, invoicer, contracts):
        """ Setup a dict with data passed to invoice.create.
            If any custom data is wanted in invoice from contract group, just
            inherit this method.
        """
        self.ensure_one()
        partner = self.partner_id
        # set context for invoice_line creation
        contracts = contracts.with_context(journal_id=journal.id,
                                           type='out_invoice')
        inv_data = {
            'account_id': partner.property_account_receivable_id.id,
            'type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': journal.id,
            'payment_term_id': self.env.ref(
                'account.account_payment_term_immediate').id,
            'currency_id':
            partner.property_product_pricelist.currency_id.id,
            'date_invoice': self.next_invoice_date,
            'recurring_invoicer_id': invoicer.id,
            'payment_mode_id': self.payment_mode_id.id,
            'invoice_line_ids': [
                (0, 0, invl) for invl in contracts.get_inv_lines_data() if invl
            ]
        }
        return inv_data
