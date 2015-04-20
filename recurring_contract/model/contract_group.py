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

from openerp.osv import orm, fields
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from openerp.tools.translate import _

import logging
import pdb

logger = logging.getLogger(__name__)


class contract_group(orm.Model):
    _name = 'recurring.contract.group'
    _description = 'A group of contracts'
    _inherit = 'mail.thread'
    _rec_name = 'ref'

    def _get_gen_states(self):
        return ['active']

    def _get_next_invoice_date(self, cr, uid, ids, name, args, context=None):
        res = {}
        for group in self.browse(cr, uid, ids, context):
            res[group.id] = min([c.next_invoice_date
                                 for c in group.contract_ids
                                 if c.state in self._get_gen_states()] or
                                [False])
        return res

    def _get_last_paid_invoice(self, cr, uid, ids, name, args, context=None):
        res = dict()
        for group in self.browse(cr, uid, ids, context):
            res[group.id] = max([c.last_paid_invoice_date
                                 for c in group.contract_ids] or [False])
        return res

    def _get_groups_from_contract(self, cr, uid, ids, context=None):
        group_ids = set()
        contract_obj = self.pool.get('recurring.contract')
        for contract in contract_obj.browse(cr, uid, ids, context):
            group_ids.add(contract.group_id.id)
        return list(group_ids)

    _columns = {
        # TODO sequence for name/ref ?
        'ref': fields.char(_('Reference')),
        'recurring_unit': fields.selection([
            ('day', _('Day(s)')),
            ('week', _('Week(s)')),
            ('month', _('Month(s)')),
            ('year', _('Year(s)'))], _('Reccurency'), required=True,
            track_visibility="onchange"),
        'recurring_value': fields.integer(
            _('Generate every'), required=True, track_visibility="onchange"),
        'partner_id': fields.many2one(
            'res.partner', _('Partner'), required=True,
            ondelete='cascade', track_visibility="onchange"),
        'contract_ids': fields.one2many(
            'recurring.contract', 'group_id', _('Contracts'),
            readonly=True),
        'advance_billing_months': fields.integer(
            _('Advance billing months'),
            help=_(
                'Advance billing allows you to generate invoices in '
                'advance. For example, you can generate the invoices '
                'for each month of the year and send them to the '
                'customer in january.'
                ),
            track_visibility="onchange", ondelete='no action'),
        'payment_term_id': fields.many2one('account.payment.term',
                                           _('Payment Term'),
                                           track_visibility="onchange"),
        'next_invoice_date': fields.function(
            _get_next_invoice_date, type='date',
            string=_('Next invoice date'),
            store={
                'recurring.contract': (
                    _get_groups_from_contract, ['next_invoice_date',
                                                'state'], 20),
            }),
        'last_paid_invoice_date': fields.function(
            _get_last_paid_invoice, type='date',
            string=_('Last paid invoice date')
        )
    }

    _defaults = {
        'ref': '/',
        'recurring_unit': 'month',
        'recurring_value': 1,
        'advance_billing_months': 1,
    }

    def _get_contract_ids(self, cr, uid, ids, context=None):
        contract_ids = list()

        for contract_group_id in self.browse(cr, uid, ids, context):
            for contract in contract_group_id.contract_ids:
                if contract.id not in contract_ids:
                    contract_ids.append(contract.id)
        return contract_ids

    def write(self, cr, uid, ids, vals, context=None):

        recurring_contract_obj = self.pool.get('recurring.contract')
        contract_ids = self._get_contract_ids(cr, uid, ids, context)

        if ('advance_billing_months' in vals):
            old_advance_billing_months = self.browse(
                cr, uid, ids, context)[0].advance_billing_months
            if old_advance_billing_months > vals['advance_billing_months']:
                pdb.set_trace()
                self._on_advance_billing_changed(
                    cr, uid, contract_ids,
                    vals['advance_billing_months'],
                    context)
                since_date = datetime.today() + \
                    relativedelta(months=+vals['advance_billing_months'])
                recurring_contract_obj.clean_invoices(
                    cr, uid, contract_ids, context=context,
                    since_date=since_date)

            self.button_generate_invoices(cr, uid, ids, context=context)

        if ('recurring_value' in vals or
                'recurring_unit' in vals):
            self.button_generate_invoices(cr, uid, ids, context=context)

        res = super(contract_group, self).write(cr, uid, ids, vals, context)
        return res

    def _on_next_invoice_change(
            self, cr, uid, ids, new_invoice_date, context=None):
        for group in self.browse(cr, uid, ids, context):
            if (group.last_paid_invoice_date > new_invoice_date or
                    datetime.today() > new_invoice_date):
                raise orm.except_orm(
                    'Error',
                    _('You cannot set the next invoice date'
                      'at {}.'.format(new_invoice_date)))
                break
        else:
            vals = dict()
            vals['next_invoice_date'] = new_invoice_date
            super(contract_group, self).write(cr, uid, ids, vals, context)

    def _on_advance_billing_changed(
            self, cr, uid, contract_ids, adv_billing, context=None):
        contract_obj = self.pool.get('recurring.contract')
        delta = relativedelta(months=+adv_billing)

        for contract in contract_obj.browse(cr, uid, contract_ids, context):
            next_invoice_date = datetime.today() + delta
            last_paid_invoice_date = contract.last_paid_invoice_date

            if last_paid_invoice_date:
                next_invoice_date = max(
                    [last_paid_invoice_date, datetime.today()]) + delta

            contract_obj.write(
                cr, uid, [contract.id],
                {'next_invoice_date': datetime.strftime(
                    next_invoice_date, DF)},
                context)

    def button_generate_invoices(self, cr, uid, ids, context=None):
        invoicer_id = self.generate_invoices(cr, uid, ids, context=context)

        recurring_invoicer_obj = self.pool.get('recurring.invoicer')
        recurring_invoicer = recurring_invoicer_obj.browse(
            cr, uid, invoicer_id, context)

        # Check if there is invoice waiting for validation
        if recurring_invoicer.invoice_ids:
            self.pool.get('recurring.invoicer').validate_invoices(
                cr, uid, [invoicer_id])

    def generate_invoices(self, cr, uid, ids, invoicer_id=None, context=None):
        ''' Checks all contracts and generate invoices if needed.
        Create an invoice per contract group per date.
        '''
        logger.info("Invoice generation started.")
        inv_obj = self.pool.get('account.invoice')
        journal_obj = self.pool.get('account.journal')
        contract_obj = self.pool.get('recurring.contract')

        if not ids:
            ids = self.search(cr, uid, [], context=context)

        if not invoicer_id:
            invoicer_id = self.pool.get('recurring.invoicer').create(
                cr, uid, {}, context)

        journal_ids = journal_obj.search(
            cr, uid, [('type', '=', 'sale'), ('company_id', '=', 1 or False)],
            limit=1)

        # Invoice lines are generated for an active contract
        # If group.next_inv_date <= today
        #   and contr.next_inv_date <= group.next_inv_date
        #   or (group.next_inv_date > today
        #      and contr.next_inv_date <= group.next_inv_date + adv_billing
        #      and contract had an invoice generated in the process)
        #
        # The last condition ensures that we won't start to do advance billing
        # for contract who had initial next_invoice_date > today.
        nb_groups = len(ids)
        count = 1
        for group_id in ids:
            logger.info("Generating invoices for group {0}/{1}".format(
                count, nb_groups))
            contract_group = self.browse(cr, uid, group_id, context)
            month_delta = contract_group.advance_billing_months or 1
            limit_date = datetime.today() + relativedelta(months=+month_delta)
            while True:  # Emulate a do-while loop
                # contract_group update 'cause next_inv_date has been modified
                contract_group = self.browse(cr, uid, group_id, context)
                group_inv_date = contract_group.next_invoice_date
                contr_ids = []
                if group_inv_date and datetime.strptime(group_inv_date,
                                                        DF) <= limit_date:
                    contr_ids = [c.id
                                 for c in contract_group.contract_ids
                                 if c.next_invoice_date <= group_inv_date and
                                 c.state in self._get_gen_states()]
                if not contr_ids:
                    break

                inv_data = self._setup_inv_data(cr, uid, contract_group,
                                                journal_ids, invoicer_id,
                                                context=context)
                invoice_id = inv_obj.create(cr, uid, inv_data, context=context)
                pdb.set_trace()
                for contract in contract_obj.browse(cr, uid, contr_ids,
                                                    context):
                    self._generate_invoice_lines(cr, uid, contract, invoice_id,
                                                 context)
                inv_obj.button_compute(cr, uid, [invoice_id], context=context)
            # After a contract_group is done, we commit all writes in order to
            # avoid doing it again in case of an error or a timeout
            cr.commit()
            count += 1
        logger.info("Invoice generation successfully finished.")
        return invoicer_id

    def _setup_inv_data(self, cr, uid, con_gr, journal_ids,
                        invoicer_id, context=None):
        ''' Setup a dict with data passed to invoice.create.
            If any custom data is wanted in invoice from contract group, just
            inherit this method.
        '''
        partner = con_gr.partner_id

        inv_data = {
            'account_id': partner.property_account_receivable.id,
            'type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': len(journal_ids) and journal_ids[0] or False,
            'currency_id':
            partner.property_product_pricelist.currency_id.id or False,
            'date_invoice': con_gr.next_invoice_date,
            'recurring_invoicer_id': invoicer_id,
            'payment_term': con_gr.payment_term_id and
            con_gr.payment_term_id.id or False,
        }

        return inv_data

    def _setup_inv_line_data(self, cr, uid, contract_line, invoice_id,
                             context=None):
        ''' Setup a dict with data passed to invoice_line.create.
        If any custom data is wanted in invoice line from contract,
        just inherit this method.
        '''
        product = contract_line.product_id

        inv_line_data = {
            'name': product.name,
            'account_id': product.property_account_income.id,
            'price_unit': contract_line.amount or 0.0,
            'quantity': contract_line.quantity,
            'uos_id': False,
            'product_id': product.id or False,
            'invoice_id': invoice_id,
            'contract_id': contract_line.contract_id.id,
        }

        return inv_line_data

    def _generate_invoice_lines(self, cr, uid, contract, invoice_id,
                                context=None):
        inv_line_obj = self.pool.get('account.invoice.line')
        for contract_line in contract.contract_line_ids:
            inv_line_data = self._setup_inv_line_data(cr, uid, contract_line,
                                                      invoice_id, context)
            inv_line_obj.create(cr, uid, inv_line_data, context=context)

        if not context.get('no_next_date_update'):
            vals = {}
            contract_obj = self.pool.get('recurring.contract')
            next_date = contract_obj._compute_next_invoice_date(contract)
            vals['next_invoice_date'] = next_date.strftime(DF)
            contract_obj.write(cr, uid, [contract.id], vals, context)
