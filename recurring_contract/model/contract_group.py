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

import openerp
from openerp import api, fields, models
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from openerp.tools.translate import _
import logging
logger = logging.getLogger(__name__)


class contract_group(models.Model):
    _name = 'recurring.contract.group'
    _description = 'A group of contracts'
    _inherit = 'mail.thread'
    _rec_name = 'ref'

    def _get_change_methods(self):
        """ Method for applying changes """
        return [
            ('do_nothing',
             'Nothing'),
            ('clean_invoices',
             'Clean invoices')
        ]

    def __get_change_methods(self):
        """ Call method which can be inherited """
        return self._get_change_methods()

    def _get_gen_states(self):
        return ['active']

    @api.depends('contract_ids.next_invoice_date', 'contract_ids.state')
    def _get_next_invoice_date(self):
        next_inv_date = min(
            [c.next_invoice_date for c in self.contract_ids
             if c.state in self._get_gen_states()] or [False])
        self.next_invoice_date = next_inv_date

    def _get_last_paid_invoice(self):
        res = dict()
        for group in self:
            res[group.id] = max([c.last_paid_invoice_date
                                 for c in group.contract_ids] or [False])
        return res

    def _get_groups_from_contract(self):
        group_ids = set()
        contract_obj = self.env['recurring.contract']
        for contract in contract_obj.browse(self.id):
            group_ids.add(contract.group_id.id)
        return list(group_ids)

    partner_id = fields.Many2one(
        'res.partner', _('Partner'), required=True,
        ondelete='cascade', track_visibility="onchange")

    ref = fields.Char(_('Reference'), default="/")
    recurring_unit = fields.Selection([
        ('day', _('Day(s)')),
        ('week', _('Week(s)')),
        ('month', _('Month(s)')),
        ('year', _('Year(s)'))], _('Reccurency'),
        default='month', required=True)
    recurring_value = fields.Integer(
        _('Generate every'), default=1, required=True)
    contract_ids = fields.One2many(
        'recurring.contract', 'group_id', _('Contracts'), readonly=True)
    # TODO Add unit for advance_billing
    advance_billing_months = fields.Integer(
        _('Advance billing months'),
        help=_(
            'Advance billing allows you to generate invoices in '
            'advance. For example, you can generate the invoices '
            'for each month of the year and send them to the '
            'customer in january.'
        ), default=1, ondelete='no action')
    payment_term_id = fields.Many2one('account.payment.term',
                                      _('Payment Term'),
                                      track_visibility="onchange")

    next_invoice_date = fields.Date(
        compute='_get_next_invoice_date',
        string=_('Next invoice date'), store=True)

    last_paid_invoice_date = fields.Date(
        compute='_get_last_paid_invoice',
        string=_('Last paid invoice date'))

    change_method = fields.Selection(
        selection=__get_change_methods, default='do_nothing',
        string=_('Change method'))

    def write(self, vals):
        """
            Perform various check at contract modifications
            - Advance billing increased or decrease
            - Recurring value or unit changes
            - Another change method was selected
        """
        res = True
        # to solve "NotImplementedError: Iteration is not allowed" error
        # Any of these modifications implies generate and validate invoices
        generate_again = ('advance_billing_months' in vals or
                          'recurring_value' in vals or
                          'recurring_unit' in vals)

        for group in self:

            # Check if group has an next_invoice_date
            if not group.next_invoice_date:
                res = super(contract_group, self).write(vals) and res
                break

            # Get the method to apply changes
            change_method = vals.get('change_method', group.change_method)
            change_method = getattr(self, change_method)

            res = super(contract_group, self).write(vals) & res

            if generate_again:
                change_method()

        if generate_again:
            invoicer_id = self.generate_invoices()
            self.validate_invoices(invoicer_id)

        return res

    def button_generate_invoices(self):
        invoicer_id = self.generate_invoices()
        self.validate_invoices(invoicer_id)
        return invoicer_id

    @api.one
    def validate_invoices(self, invoicer_id):
        # Check if there is invoice waiting for validation
        if invoicer_id.invoice_ids:
            invoicer_id.validate_invoices()

    def clean_invoices(self):
        """ Change method which cancels generated invoices and rewinds
        the next_invoice_date of contracts, so that new invoices can be
        generated taking into consideration the modifications of the
        contract group.
        """
        since_date = datetime.date.today()
        if self.last_paid_invoice_date:
            last_paid_invoice_date = datetime.strptime(
                self.last_paid_invoice_date, DF)
            since_date = max(since_date, last_paid_invoice_date)
        res = self.contract_ids.clean_invoices(since_date=since_date)
        self.contract_ids.rewind_next_invoice_date()
        return res

    def do_nothing(self):
        """ No changes before generation """
        pass

    def generate_invoices(self, invoicer_id=None):
        """ Checks all contracts and generate invoices if needed.
        Create an invoice per contract group per date.
        """
        logger.info("Invoice generation started.")
        inv_obj = self.env['account.invoice']
        journal_obj = self.env['account.journal']
        gen_states = self._get_gen_states()
        if not invoicer_id:
            invoicer_id = self.env['recurring.invoicer'].create(
                {'source': self._name})

        journal_ids = journal_obj.search(
            [('type', '=', 'sale'), ('company_id', '=', 1 or False)], limit=1)

        nb_groups = len(self)
        count = 1
        for contract_group in self:
            logger.info("Generating invoices for group {0}/{1}".format(
                count, nb_groups))
            month_delta = contract_group.advance_billing_months or 1
            limit_date = datetime.today() + relativedelta(months=+month_delta)
            while True:  # Emulate a do-while loop
                # contract_group update 'cause next_inv_date has been modified
                group_inv_date = contract_group.next_invoice_date
                contracts = []
                if group_inv_date and datetime.strptime(group_inv_date,
                                                        DF) <= limit_date:
                    contracts = [c
                                 for c in contract_group.contract_ids
                                 if c.next_invoice_date <= group_inv_date and
                                 c.state in gen_states]
                if not contracts:
                    break
                inv_data = contract_group._setup_inv_data(journal_ids,
                                                          invoicer_id)
                invoice = inv_obj.create(inv_data)
                for contract in contracts:
                    contract_group._generate_invoice_lines(contract, invoice)
                if invoice.invoice_line:
                    invoice.button_compute()
                else:
                    invoice.unlink()

            # After a contract_group is done, we commit all writes in order to
            # avoid doing it again in case of an error or a timeout
            self.env.cr.commit()
            count += 1
        logger.info("Invoice generation successfully finished.")
        return invoicer_id

    def _setup_inv_data(self, journal_ids, invoicer):
        """ Setup a dict with data passed to invoice.create.
            If any custom data is wanted in invoice from contract group, just
            inherit this method.
        """
        partner = self.partner_id
        inv_data = {
            'account_id': partner.property_account_receivable.id,
            'type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': len(journal_ids) and journal_ids[0].id or False,
            'currency_id':
            partner.property_product_pricelist.currency_id.id or False,
            'date_invoice': self.next_invoice_date,
            'recurring_invoicer_id': invoicer.id,
            'payment_term': self.payment_term_id and
            self.payment_term_id.id or False,
        }

        return inv_data

    def _setup_inv_line_data(self, contract_line, invoice):
        """ Setup a dict with data passed to invoice_line.create.
        If any custom data is wanted in invoice line from contract,
        just inherit this method.
        """
        product = contract_line.product_id
        account = product.property_account_income
        inv_line_data = {
            'name': product.name,
            'price_unit': contract_line.amount or 0.0,
            'quantity': contract_line.quantity,
            'uos_id': False,
            'product_id': product.id or False,
            'invoice_id': invoice.id,
            'contract_id': contract_line.contract_id.id,
        }
        if account:
            inv_line_data['account_id'] = account.id
        return inv_line_data

    @api.one
    def _generate_invoice_lines(self, contract, invoice):
        inv_line_obj = self.env['account.invoice.line']
        for contract_line in contract.contract_line_ids:
            inv_line_data = self._setup_inv_line_data(contract_line, invoice)
            if inv_line_data:
                inv_line_obj.create(inv_line_data)

        if not self.env.context.get('no_next_date_update'):
            contract.update_next_invoice_date()
