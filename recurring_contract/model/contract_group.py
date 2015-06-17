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
logger = logging.getLogger(__name__)


class contract_group(orm.Model):
    _name = 'recurring.contract.group'
    _description = 'A group of contracts'
    _inherit = 'mail.thread'
    _rec_name = 'ref'

    def _get_change_methods(self, cr, uid, context=None):
        """ Method for applying changes """
        return [
            ('do_nothing',
             'Nothing'),
            ('clean_invoices',
             'Clean invoices')
        ]

    def __get_change_methods(self, cr, uid, context=None):
        """ Call method which can be inherited """
        return self._get_change_methods(cr, uid, context=context)

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
            ('year', _('Year(s)'))], _('Reccurency'), required=True),
        'recurring_value': fields.integer(
            _('Generate every'), required=True),
        'partner_id': fields.many2one(
            'res.partner', _('Partner'), required=True,
            ondelete='cascade', track_visibility="onchange"),
        'contract_ids': fields.one2many(
            'recurring.contract', 'group_id', _('Contracts'),
            readonly=True),
        # TODO Add unit for advance_billing
        'advance_billing_months': fields.integer(
            _('Advance billing months'),
            help=_(
                'Advance billing allows you to generate invoices in '
                'advance. For example, you can generate the invoices '
                'for each month of the year and send them to the '
                'customer in january.'
            ), ondelete='no action'),
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
        ),
        'change_method': fields.selection(
            __get_change_methods, 'Change method'),
    }

    _defaults = {
        'ref': '/',
        'recurring_unit': 'month',
        'recurring_value': 1,
        'advance_billing_months': 1,
        'change_method': 'do_nothing',
    }

    def write(self, cr, uid, ids, vals, context=None):
        """
            Perform various check at contract modifications
            - Advance billing increased or decrease
            - Recurring value or unit changes
            - Another change method was selected
        """
        res = True
        # to solve "NotImplementedError: Iteration is not allowed" error
        if isinstance(ids, (int, long)):
            ids = [ids]

        # Any of these modifications implies generate and validate invoices
        generate_again = ('advance_billing_months' in vals or
                          'recurring_value' in vals or
                          'recurring_unit' in vals)

        for group in self.browse(cr, uid, ids, context):

            # Check if group has an next_invoice_date
            if not group.next_invoice_date:
                res = super(contract_group, self).write(
                    cr, uid, group.id, vals, context) and res
                break

            # Get the method to apply changes
            change_method = vals.get('change_method', group.change_method)
            change_method = getattr(self, change_method)

            res = super(contract_group, self).write(
                cr, uid, group.id, vals, context) & res

            if generate_again:
                change_method(cr, uid, group, context)

        if generate_again:
            invoicer_id = self.generate_invoices(cr, uid, ids,
                                                 context=context)
            self.validate_invoices(cr, uid, invoicer_id, context)

        return res

    def button_generate_invoices(self, cr, uid, ids, context=None):
        invoicer_id = self.generate_invoices(cr, uid, ids, context=context)
        self.validate_invoices(cr, uid, invoicer_id, context)
        return invoicer_id

    def validate_invoices(self, cr, uid, invoicer_id, context=None):
        recurring_invoicer_obj = self.pool.get('recurring.invoicer')
        recurring_invoicer = recurring_invoicer_obj.browse(
            cr, uid, invoicer_id, context)

        # Check if there is invoice waiting for validation
        if recurring_invoicer.invoice_ids:
            self.pool.get('recurring.invoicer').validate_invoices(
                cr, uid, [invoicer_id])

    def clean_invoices(self, cr, uid, group, context=None):
        """ Change method which cancels generated invoices and rewinds
        the next_invoice_date of contracts, so that new invoices can be
        generated taking into consideration the modifications of the
        contract group.
        """

        recurring_contract_obj = self.pool.get('recurring.contract')
        contract_ids = [contract.id for contract in group.contract_ids]
        since_date = datetime.today()
        if group.last_paid_invoice_date:
            last_paid_invoice_date = datetime.strptime(
                group.last_paid_invoice_date, DF)
            since_date = max(since_date, last_paid_invoice_date)
        res = recurring_contract_obj.clean_invoices(
            cr, uid, contract_ids, context=context,
            since_date=since_date)
        recurring_contract_obj.rewind_next_invoice_date(
            cr, uid, contract_ids, context)
        return res

    def do_nothing(self, cr, uid, group, context=None):
        """ No changes before generation """
        pass

    def generate_invoices(self, cr, uid, ids, invoicer_id=None, context=None):
        """ Checks all contracts and generate invoices if needed.
        Create an invoice per contract group per date.
        """
        if context is None:
            context = dict()
        logger.info("Invoice generation started.")
        inv_obj = self.pool.get('account.invoice')
        journal_obj = self.pool.get('account.journal')
        contract_obj = self.pool.get('recurring.contract')
        gen_states = self._get_gen_states()

        if not ids:
            ids = self.search(cr, uid, [], context=context)
        if not invoicer_id:
            invoicer_id = self.pool.get('recurring.invoicer').create(
                cr, uid, {'source': self._name}, context)

        journal_ids = journal_obj.search(
            cr, uid, [('type', '=', 'sale'), ('company_id', '=', 1 or False)],
            limit=1)
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
                                 c.state in gen_states]
                if not contr_ids:
                    break

                inv_data = self._setup_inv_data(cr, uid, contract_group,
                                                journal_ids, invoicer_id,
                                                context=context)

                invoice_id = inv_obj.create(cr, uid, inv_data, context=context)
                for contract in contract_obj.browse(cr, uid, contr_ids,
                                                    context):
                    self._generate_invoice_lines(cr, uid, contract, invoice_id,
                                                 context)
                invoice = inv_obj.browse(cr, uid, invoice_id, context)
                if invoice.invoice_line:
                    invoice.button_compute()
                else:
                    invoice.unlink()
            # After a contract_group is done, we commit all writes in order to
            # avoid doing it again in case of an error or a timeout
            cr.commit()
            count += 1
        logger.info("Invoice generation successfully finished.")
        return invoicer_id

    def _setup_inv_data(self, cr, uid, con_gr, journal_ids,
                        invoicer_id, context=None):
        """ Setup a dict with data passed to invoice.create.
            If any custom data is wanted in invoice from contract group, just
            inherit this method.
        """
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
        """ Setup a dict with data passed to invoice_line.create.
        If any custom data is wanted in invoice line from contract,
        just inherit this method.
        """
        product = contract_line.product_id
        account_id = product.property_account_income
        inv_line_data = {
            'name': product.name,
            'price_unit': contract_line.amount or 0.0,
            'quantity': contract_line.quantity,
            'uos_id': False,
            'product_id': product.id or False,
            'invoice_id': invoice_id,
            'contract_id': contract_line.contract_id.id,
        }
        if account_id:
            inv_line_data['account_id'] = account_id.id
        return inv_line_data

    def _generate_invoice_lines(self, cr, uid, contract, invoice_id,
                                context=None):
        inv_line_obj = self.pool.get('account.invoice.line')
        for contract_line in contract.contract_line_ids:
            inv_line_data = self._setup_inv_line_data(cr, uid, contract_line,
                                                      invoice_id, context)
            if inv_line_data:
                inv_line_obj.create(cr, uid, inv_line_data, context=context)

        if not context.get('no_next_date_update'):
            contract.update_next_invoice_date()
