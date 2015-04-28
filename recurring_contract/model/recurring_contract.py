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
from openerp import netsvc
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp


class res_partner(orm.Model):

    """ Override partners to add contract m2o relation. Raise an error if
    we try to delete a partner with active contracts.
    """
    _inherit = 'res.partner'

    _columns = {
        'contract_group_ids': fields.one2many(
            'recurring.contract.group', 'partner_id',
            _('Contract groups')),
    }

    def unlink(self, cr, uid, ids, context=None):
        """ Raise an error if there is active contracts for partner """
        if context is None:
            context = {}
        partners = self.browse(cr, uid, ids, context=context)
        unlink_ids = []

        for partner in partners:
            for contract_group in partner.contract_group_ids:
                for contract in contract_group.contract_ids:
                    if contract.state not in ('draft', 'terminated'):
                        raise orm.except_orm(
                            'UserError',
                            _('You cannot delete a partner having an active '
                              'contract.'))
            unlink_ids.append(partner.id)

        super(res_partner, self).unlink(cr, uid, unlink_ids, context=context)
        return True


class recurring_contract_line(orm.Model):

    """ Each product sold through a contract """
    _name = "recurring.contract.line"
    _description = "A contract line"

    def name_get(self, cr, uid, ids, context=None):
        if not ids:
            return []
        res = [(cl.id, cl.product_id.name_template) for cl in self.browse(
               cr, uid, ids, context)]
        return res

    def _compute_subtotal(self, cr, uid, ids, field_name, arg, context):
        res = {}
        for line in self.browse(cr, uid, ids, context=context):
            price = line.amount * line.quantity
            res[line.id] = price
        return res

    _columns = {
        'contract_id': fields.many2one(
            'recurring.contract', _('Contract'), required=True,
            ondelete='cascade', readonly=True),
        'product_id': fields.many2one(
            'product.product', _('Product'), required=True),
        'amount': fields.float(_('Price'), required=True),
        'quantity': fields.integer(_('Quantity'), required=True),
        'subtotal': fields.function(
            _compute_subtotal, string='Subtotal', type="float",
            digits_compute=dp.get_precision('Account'), store=True),
    }

    _defaults = {
        'quantity': 1,
    }

    def on_change_product_id(self, cr, uid, ids, product_id, context=None):
        if not context:
            context = {}

        if not product_id:
            return {'value': {'amount': 0.0}}

        prod = self.pool.get('product.product').browse(cr, uid, product_id,
                                                       context)
        value = {'amount': prod.list_price or 0.0}
        return {'value': value}


class recurring_contract(orm.Model):

    ''' A contract to perform recurring invoicing to a partner '''
    _name = "recurring.contract"
    _description = "Contract for recurring invoicing"
    _inherit = ['mail.thread']
    _rec_name = 'reference'

    def _get_total_amount(self, cr, uid, ids, name, args, context=None):
        total = {}
        for contract in self.browse(cr, uid, ids, context):
            total[contract.id] = sum([line.subtotal
                                      for line in contract.contract_line_ids])
        return total

    def _get_last_paid_invoice(self, cr, uid, ids, name, args, context=None):
        res = dict()
        for contract in self.browse(cr, uid, ids, context):
            res[contract.id] = max([invl.due_date
                                    for invl in contract.invoice_line_ids
                                    if invl.state == 'paid'] or [False])
        return res

    _columns = {
        'reference': fields.char(
            _('Reference'), required=True, readonly=True,
            states={'draft': [('readonly', False)]}),
        'start_date': fields.date(
            _('Start date'), required=True, readonly=True,
            states={'draft': [('readonly', False)]},
            track_visibility="onchange"),
        'end_date': fields.date(
            _('End date'), readonly=False,
            states={'terminated': [('readonly', True)]},
            track_visibility="onchange"),
        'next_invoice_date': fields.date(
            _('Next invoice date'), readonly=False,
            states={'draft': [('readonly', False)]}),
        'last_paid_invoice_date': fields.function(
            _get_last_paid_invoice, type='date',
            string=_('Last paid invoice date')),
        'partner_id': fields.many2one(
            'res.partner', string=_('Partner'), required=True,
            readonly=True, states={'draft': [('readonly', False)]},
            ondelete='restrict'),
        'group_id': fields.many2one(
            'recurring.contract.group', _('Payment Options'),
            required=True, ondelete='cascade',
            track_visibility="onchange"),
        'invoice_line_ids': fields.one2many(
            'account.invoice.line', 'contract_id',
            _('Related invoice lines'), readonly=True),
        'contract_line_ids': fields.one2many(
            'recurring.contract.line', 'contract_id',
            _('Contract lines'), track_visibility="onchange"),
        'state': fields.selection([
            ('draft', _('Draft')),
            ('active', _('Active')),
            ('terminated', _('Terminated'))], _('Status'), select=True,
            readonly=True, track_visibility='onchange',
            help=_(" * The 'Draft' status is used when a user is encoding a "
                   "new and unconfirmed Contract.\n"
                   "* The 'Active' status is used when the contract is "
                   "confirmed and until it's terminated.\n"
                   "* The 'Terminated' status is used when a contract is no "
                   "longer active.")),
        'total_amount': fields.function(
            _get_total_amount, string='Total',
            digits_compute=dp.get_precision('Account'),
            store={
                'recurring.contract': (lambda self, cr, uid, ids, c={}:
                                       ids, ['contract_line_ids'], 20),
            }, track_visibility="onchange"),
        'payment_term_id': fields.related(
            'group_id', 'payment_term_id', relation='account.payment.term',
            type="many2one", readonly=True, string=_('Payment Term'),
            store=True),
    }

    _defaults = {
        'reference': '/',
        'state': 'draft',
        'start_date': datetime.today().strftime(DF),
    }

    def _check_unique_reference(self, cr, uid, ids, context=None):
        sr_ids = self.search(cr, 1, [], context=context)
        lst = [contract.reference
               for contract in self.browse(cr, uid, sr_ids, context=context)
               if contract.reference and contract.id not in ids]
        for self_contract in self.browse(cr, uid, ids, context=context):
            if self_contract.reference and self_contract.reference in lst:
                return False
        return True

    _constraints = [(_check_unique_reference,
                     _('Error: Reference should be unique'), ['reference'])]

    #################################
    #        PUBLIC METHODS         #
    #################################
    def create(self, cr, uid, vals, context=None):
        """ Add a sequence generated ref if none is given """
        if vals.get('reference', '/') == '/':
            vals['reference'] = self.pool.get('ir.sequence').next_by_code(
                cr, uid, 'recurring.contract.ref', context=context)
        return super(recurring_contract, self).create(cr, uid, vals,
                                                      context=context)

    def write(self, cr, uid, ids, vals, context=None):
        res = super(recurring_contract, self).write(
            cr, uid, ids, vals, context=context)

        """ Perform various checks when a contract is modified. """
        if 'next_invoice_date' in vals:
            self._on_change_next_invoice_date(
                cr, uid, ids, vals['next_invoice_date'], context)

        if 'contract_line_ids' in vals:
            self._on_contract_lines_changed(cr, uid, ids, context)

        return res

    def copy(self, cr, uid, id, default=None, context=None):
        default = default or {}
        start_date = self._compute_copy_start_date(cr, uid, id, context)
        default.update({
            'state': 'draft',
            'reference': '/',
            'start_date': start_date,
            'end_date': False,
            'next_invoice_date': start_date,
            'invoice_line_ids': False,
        })
        return super(recurring_contract, self).copy(cr, uid, id, default,
                                                    context)

    def _compute_copy_start_date(self, cr, uid, id, context=None):
        today = datetime.today()
        if today.day > 15:
            today = today + relativedelta(months=+1)
        today = today.replace(day=1)
        return today.strftime(DF)

    def unlink(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        contracts = self.read(cr, uid, ids, ['state'], context=context)
        unlink_ids = []

        for contract in contracts:
            if contract['state'] not in ('draft', 'terminated'):
                raise orm.except_orm(
                    'UserError',
                    _('You cannot delete a contract that is still active. '
                      'Terminate it first.'))
            else:
                unlink_ids.append(contract['id'])

        super(recurring_contract, self).unlink(cr, uid, unlink_ids,
                                               context=context)
        return

    def button_generate_invoices(self, cr, uid, ids, context=None):
        group_ids = [contract.group_id.id for contract in self.browse(
            cr, uid, ids, context)]
        contract_group_obj = self.pool.get('recurring.contract.group')
        contract_group_obj.button_generate_invoices(
            cr, uid, group_ids, context)

    def clean_invoices(self, cr, uid, ids, context=None, since_date=None,
                       to_date=None):
        """ This method deletes invoices lines generated for a given contract
            having a due date >= current month. If the invoice_line was the
            only line in the invoice, we cancel the invoice. In the other
            case, we have to revalidate the invoice to update the move lines.
        """
        invl_search = [('contract_id', 'in', ids),
                       ('state', 'not in', ('paid', 'cancel'))]
        if since_date:
            invl_search.append(('due_date', '>=', since_date))
        if to_date:
            invl_search.append(('due_date', '<=', to_date))
        inv_line_obj = self.pool.get('account.invoice.line')
        inv_obj = self.pool.get('account.invoice')
        wf_service = netsvc.LocalService('workflow')

        # Find all unpaid invoice lines after the given date
        inv_line_ids = inv_line_obj.search(cr, uid, invl_search,
                                           context=context)

        inv_ids = set()
        empty_inv_ids = set()
        to_remove_ids = []   # Invoice lines that will be removed

        for inv_line in inv_line_obj.browse(cr, uid, inv_line_ids, context):
            invoice = inv_line.invoice_id
            inv_ids.add(invoice.id)
            # Check if invoice is empty after removing the invoice_lines
            # of the given contract
            if invoice.id not in empty_inv_ids:
                other_lines_ids = [invl.id for invl in invoice.invoice_line]
                remaining_lines_ids = [invl_id for invl_id in other_lines_ids
                                       if invl_id not in inv_line_ids]
                if remaining_lines_ids:
                    # We can remove the line
                    to_remove_ids.append(inv_line.id)
                else:
                    # The invoice would be empty if we remove the line
                    empty_inv_ids.add(invoice.id)

        if inv_line_ids:  # To prevent remove all inv_lines...
            inv_line_obj.unlink(cr, uid, to_remove_ids, context)

        inv_obj.action_cancel(cr, uid, list(inv_ids), context=context)

        # Invoices to set back in open state
        renew_inv_ids = list(inv_ids - empty_inv_ids)
        inv_obj.action_cancel_draft(cr, uid, renew_inv_ids)
        for inv in inv_obj.browse(cr, uid, renew_inv_ids, context):
            wf_service.trg_validate(uid, 'account.invoice',
                                    inv.id, 'invoice_open', cr)

        for contract in self.browse(cr, uid, ids, context):
            next_invoice_date = since_date

            if contract.last_paid_invoice_date:
                next_invoice_date = max(
                    datetime.strptime(
                        contract.last_paid_invoice_date, DF), since_date)

            self.write(
                cr, uid, [contract.id],
                {'next_invoice_date': datetime.strftime(
                    next_invoice_date, DF)},
                context)

        return inv_ids

    #################################
    #        PRIVATE METHODS        #
    #################################
    def _compute_next_invoice_date(self, contract):
        next_date = datetime.strptime(contract.next_invoice_date, DF)
        rec_unit = contract.group_id.recurring_unit
        rec_value = contract.group_id.recurring_value
        if rec_unit == 'day':
            next_date = next_date + relativedelta(days=+rec_value)
        elif rec_unit == 'week':
            next_date = next_date + relativedelta(weeks=+rec_value)
        elif rec_unit == 'month':
            next_date = next_date + relativedelta(months=+rec_value)
        else:
            next_date = next_date + relativedelta(years=+rec_value)

        return next_date

    def _update_invoice_lines(self, cr, uid, contract, invoice_ids,
                              context=None):
        """Update invoice lines generated by a contract, when the contract
        was modified and corresponding invoices were cancelled.

        Parameters:
            - invoice_ids (list): ids of draft invoices to be
                                  updated and validated
        """
        invoice_obj = self.pool.get('account.invoice')
        inv_line_obj = self.pool.get('account.invoice.line')
        group_obj = self.pool.get('recurring.contract.group')
        for invoice in invoice_obj.browse(cr, uid, invoice_ids, context):
            # Update payment term and generate new invoice_lines
            invoice.write({
                'payment_term': contract.group_id.payment_term_id and
                contract.group_id.payment_term_id.id or False})
            old_lines_ids = [invl.id for invl in invoice.invoice_line
                             if invl.contract_id.id == contract.id]
            inv_line_obj.unlink(cr, uid, old_lines_ids)
            context['no_next_date_update'] = True
            group_obj._generate_invoice_lines(cr, uid, contract,
                                              invoice.id, context)
            del(context['no_next_date_update'])

    def _on_change_next_invoice_date(
            self, cr, uid, ids, new_invoice_date, context=None):
        for contract in self.browse(cr, uid, ids, context):
            if contract.next_invoice_date:
                next_invoice_date = datetime.strptime(
                    contract.next_invoice_date, DF)
                new_invoice_date = datetime.strptime(new_invoice_date, DF)
                if (next_invoice_date > new_invoice_date):
                    raise orm.except_orm(
                        'Error',
                        _('You cannot set the next invoice date'
                          'at {}.'.format(new_invoice_date)))
        else:
            return True

    def _on_contract_lines_changed(self, cr, uid, ids, context=None):
            """Update related invoices to reflect the changes to the contract.
            """
            invoice_obj = self.pool.get('account.invoice')
            inv_line_obj = self.pool.get('account.invoice.line')
            # Find all unpaid invoice lines after the given date
            since_date = datetime.today().replace(day=1).strftime(DF)
            inv_line_ids = inv_line_obj.search(
                cr, uid, [('contract_id', 'in', ids),
                          ('due_date', '>=', since_date),
                          ('state', 'not in', ('paid', 'cancel'))],
                context=context)
            con_ids = set()
            inv_ids = set()
            for inv_line in inv_line_obj.browse(
                    cr, uid, inv_line_ids, context):
                invoice = inv_line.invoice_id
                if invoice.id not in inv_ids or \
                        inv_line.contract_id.id not in con_ids:
                    con_ids.add(inv_line.contract_id.id)
                    inv_ids.add(invoice.id)
                    invoice_obj.action_cancel(cr, uid, [invoice.id], context)
                    invoice_obj.action_cancel_draft(cr, uid, [invoice.id])
                    self._update_invoice_lines(cr, uid, inv_line.contract_id,
                                               [invoice.id], context)
            wf_service = netsvc.LocalService('workflow')
            for invoice in invoice_obj.browse(cr, uid, list(inv_ids), context):
                wf_service.trg_validate(
                    uid, 'account.invoice', invoice.id, 'invoice_open', cr)

    ##########################
    #        CALLBACKS       #
    ##########################
    def on_change_start_date(self, cr, uid, ids, start_date, context=None):
        """ We automatically update next_invoice_date on start_date change """
        result = {}
        if start_date:
            result.update({'next_invoice_date': start_date})

        return {'value': result}

    def on_change_partner_id(self, cr, uid, ids, partner_id, context=None):
        """ On partner change, we update the group_id. If partner has
        only 1 group, we take it. Else, we take nothing.
        """
        group_obj = self.pool.get('recurring.contract.group')
        group_ids = group_obj.search(cr, uid,
                                     [('partner_id', '=', partner_id)],
                                     context=context)
        group_id = None
        if len(group_ids) == 1:
            group_id = group_ids[0]
        return {'value': {'group_id': group_id}}

    def contract_draft(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state': 'draft'}, context=context)
        return True

    def contract_active(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'state': 'active'}, context=context)
        return True

    def contract_terminated(self, cr, uid, ids, context=None):
        today = datetime.today().strftime(DF)
        self.write(cr, uid, ids, {'state': 'terminated', 'end_date': today})
        return True

    def end_date_reached(self, cr, uid, context=None):
        today = datetime.today().strftime(DF)
        contract_ids = self.search(cr, uid, [('state', '=', 'active'),
                                             ('end_date', '<=', today)],
                                   context=context)

        if contract_ids:
            self.contract_terminated(cr, uid, contract_ids, context=context)

        return True
