# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from openerp.osv import orm, fields
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from openerp.tools.translate import _
from openerp import netsvc

from datetime import date
import pdb


class change_attribution_wizard(orm.TransientModel):

    """
    Wizard that helps the user doing changing the attribution of a payment,
    by automatically un-reconciling related move lines, cancelling
    related invoices and proposing modification of those invoices for a
    new attribution of the payment.
    """
    _name = 'unreconcile.change.attribution.wizard'

    def _get_default_invl(self, cr, uid, context=None):
        # The ids of the move_lines are given in the context, so
        # we don't use the 'ids' fields and put [0] in it.
        return self._get_invoice_lines(cr, uid, [0], 'contract_id', '',
                                       context)[0]['invoice_line_ids']

    def _get_default_payments(self, cr, uid, context=None):
        # The ids of the move_lines are given in the context, so
        # we don't use the 'ids' fields and put [0] in it.
        return self._get_invoice_lines(cr, uid, [0], 'contract_id', '',
                                       context)[0]['payment_ids']

    def _get_default_total(self, cr, uid, context=None):
        # The ids of the move_lines are given in the context, so
        # we don't use the 'ids' fields and put [0] in it.
        return self._get_invoice_lines(cr, uid, [0], 'contract_id', '',
                                       context)[0]['amount_total']

    def _get_invoice_lines(self, cr, uid, ids, field_names, arg, context):
        move_line_obj = self.pool.get('account.move.line')
        invoice_obj = self.pool.get('account.invoice')
        invl_ids = context.get('invoice_line_ids', list())
        payment_ids = list()
        amount_total = 0.0
        active_ids = context.get('active_ids')
        if not invl_ids and active_ids:
            for mvl in move_line_obj.browse(cr, uid, active_ids,
                                            context):
                # Look for credit lines
                if mvl.credit > 0 and mvl.reconcile_id:
                    payment_ids.append(mvl.id)
                    # Find related reconciled invoices
                    invoice_ids = invoice_obj.search(cr, uid, [
                        ('move_id.line_id.reconcile_id',
                         '=', mvl.reconcile_id.id),
                        ('state', '=', 'paid'),
                        ('residual', '=', 0.0)], context=context)
                    for invoice in invoice_obj.browse(cr, uid, invoice_ids,
                                                      context):
                        amount_total += invoice.amount_total
                        invl_ids.extend(
                            [invl.id for invl in invoice.invoice_line])

        return {id: {
            'invoice_line_ids': invl_ids,
            'amount_total': amount_total,
            'payment_ids': payment_ids} for id in ids}

    def _get_computed_total(self, cr, uid, ids, field_name, arg, context):
        res = dict()
        for wizard in self.browse(cr, uid, ids, context):
            res[wizard.id] = sum([invl.price_subtotal for invl in
                                  wizard.invoice_line_ids])
        return res

    def _write_invoice_lines(self, cr, uid, ids, field_name, field_value, arg,
                             context):
        value_obj = self.pool.get('account.invoice.line')
        pdb.set_trace()
        invl_ids = list()
        for line in field_value:
            if isinstance(line, tuple):
                if line[0] == 1:  # one2many update
                    value_id = line[1]
                    value_obj.write(cr, uid, [value_id], line[2])
            elif isinstance(line, (int, long)):
                invl_ids.append(line)

        # Store invl_ids in context for updating functional field_name
        if invl_ids:
            context['invoice_line_ids'] = invl_ids

        return True

    _columns = {
        'state': fields.selection([
            ('unrec', _('Unreconcile')),
            ('rec', _('Change Lines and Reconcile'))], 'state'),
        'payment_ids': fields.function(
            _get_invoice_lines, type='one2many', obj='account.move.line',
            multi='invl'),
        'invoice_line_ids': fields.function(
            _get_invoice_lines, fnct_inv=_write_invoice_lines, type='one2many',
            obj='account.invoice.line', method=True, multi='invl',
            string=_('Related invoice lines'),
            help=_('You can directly edit the invoice lines from here if '
                   'you want to change the attribution of the payment.')),
        'amount_total': fields.function(
            _get_invoice_lines, type='float', string=_('Payment Total'),
            multi='invl', readonly=True),
        'amount_computed': fields.function(
            _get_computed_total, type='float', string=_('Total'),
            readonly=True),
        'invoice_id': fields.many2one('account.invoice', 'New invoice'),
        'operation_valid': fields.boolean('Is operation valid'),
        'comment': fields.text(_("Comment"), help=_(
            "Explain why you changed the attribution."))
    }

    _defaults = {
        'state': 'unrec',
        'invoice_line_ids': _get_default_invl,
        'payment_ids': _get_default_payments,
        'amount_total': _get_default_total,
    }

    def unreconcile(self, cr, uid, ids, context=None):
        """ Unreconcile selected payments. """
        if isinstance(ids, list):
            ids = ids[0]

        wizard = self.browse(cr, uid, ids, context)
        if not wizard.invoice_line_ids:
            raise orm.except_orm(
                _("Invalid selection"),
                _("I couldn't find any invoice to modify. Please verify "
                  "your selection."))

        active_ids = context.get('active_ids')
        move_line_obj = self.pool.get('account.move.line')
        invoice_obj = self.pool.get('account.invoice')
        invoice_line_obj = self.pool.get('account.invoice.line')
        move_line_obj._remove_move_reconcile(cr, uid, active_ids,
                                             context=context)

        new_invoice_id = False
        for invoice_line in wizard.invoice_line_ids:
            invoice = invoice_line.invoice_id
            if invoice.state == 'open':
                if not new_invoice_id:
                    # We copy the first invoice to create a new one holding
                    # all modifications. The other invoices will be cancelled.
                    today = date.today().strftime(DF)
                    invoice_obj.copy(cr, uid, invoice.id, {
                        'date_invoice': today,
                        'comment': wizard.comment or 'New invoice after '
                        'payment attribution changed.',
                        'invoice_line': False}, context)
                    new_invoice_id = invoice_obj.search(cr, uid, [
                        ('partner', '=', invoice.partner_id.id),
                        ('state', '=', 'draft'),
                        ('date_invoice', '=', today)], context=context)[0]

                invoice_obj.action_cancel(cr, uid, [invoice.id], context)
                invoice.write({'comment': wizard.comment or
                               'Payment attribution changed.'})
                invl_ids = [invl.id for invl in invoice.invoice_line]
                for id in invl_ids:
                    invoice_line_obj.copy(cr, uid, id, {
                        'invoice_id': new_invoice_id}, context)

        new_invoice = invoice_obj.browse(cr, uid, new_invoice_id, context)
        new_inv_lines = [invl.id for invl in new_invoice.invoice_line]
        wizard.write({
            'state': 'rec',
            'invoice_id': new_invoice_id,
            'invoice_line_ids': [(6, 0, new_inv_lines)]})

        return {
            'name': _('Change attribution'),
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': wizard.id,
            'view_mode': 'form',
            'view_type': 'form',
            'context': context,
            'target': 'new',
        }

    def reconcile(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]

        wizard = self.browse(cr, uid, ids, context)
        active_ids = context.get('active_ids')
        move_line_obj = self.pool.get('account.move.line')

        # Validate the invoice
        wf_service = netsvc.LocalService('workflow')
        invoice = wizard.invoice_id
        wf_service.trg_validate(uid, 'account.invoice', invoice.id,
                                'invoice_open', cr)

        # Reconcile all related move lines
        move_line_ids = move_line_obj.search(
            cr, uid, [('move_id', '=', invoice.move_id.id)],
            context=context)
        move_line_ids.extend([mvl.id for mvl in wizard.payment_ids])
        move_line_obj.reconcile(cr, uid, active_ids, 'manual',
                                context=context)

        return True
