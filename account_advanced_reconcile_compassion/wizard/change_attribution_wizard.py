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


class change_attribution_wizard(orm.TransientModel):
    """
    Wizard that helps the user doing changing the attribution of a payment,
    by automatically un-reconciling related move lines, cancelling
    related invoices and proposing modification of those invoices for a
    new attribution of the payment.
    """
    _name = 'unreconcile.change.attribution.wizard'

    ##########################################################################
    #                             FIELDS METHODS                             #
    ##########################################################################
    def _get_default_invl(self, cr, uid, context=None):
        return self._get_invoice_lines(cr, uid, [0], 'invoice_line_ids', '',
                                       context)[0]

    def _get_default_total(self, cr, uid, context=None):
        return self._get_amount_total(cr, uid, [0], 'amount_total', '',
                                      context)[0]

    def _get_invoice_lines(self, cr, uid, ids, field_name, arg, context):
        """Returns the invoice line ids that can be updated.
        Context can either hold invoice ids or move line ids
        depending from where the user called the wizard.
        """
        # If wizard is already linked to new invoice, return its lines.
        wizard = self._get_wizard(cr, uid, ids, context)
        if wizard and wizard.invoice_id:
            invl_ids = [invl.id for invl in wizard.invoice_id.invoice_line]
            return {id: invl_ids for id in ids}

        # Otherwise, retrieve the paid invoice lines from context
        invl_ids = list()
        active_ids = context.get('active_ids')
        if not invl_ids and active_ids:
            model = context.get('active_model')
            if model == 'account.move.line':
                invl_ids = self._get_invl_ids_from_mvl_ids(
                    cr, uid, active_ids, context)

            elif model == 'account.invoice':
                invoice_obj = self.pool.get('account.invoice')
                for inv in invoice_obj.browse(cr, uid, active_ids, context):
                    mvl_ids = [p.id for p in inv.payment_ids]
                    invl_ids.extend(self._get_invl_ids_from_mvl_ids(
                        cr, uid, mvl_ids, context))

        return {id: list(set(invl_ids)) for id in ids}

    def _get_amount_total(self, cr, uid, ids, field_name, arg, context):
        """ Returns the total paid amount. """
        mvl_obj = self.pool.get('account.move.line')
        mvl_ids = self._get_payment_ids(cr, uid, ids, 'invoice_line_ids',
                                        '', context)[ids[0]]
        amount_total = context.get('amount_total', 0.0)
        if not amount_total:
            for mvl in mvl_obj.browse(cr, uid, mvl_ids, context):
                amount_total += mvl.credit

        return {id: amount_total for id in ids}

    def _get_payment_ids(self, cr, uid, ids, field_name, arg, context):
        """ Returns all the payments move_line ids. """
        payment_ids = context.get('payment_ids', list())
        active_ids = context.get('active_ids')
        if not payment_ids and active_ids:
            mvl_obj = self.pool.get('account.move.line')
            invoice_obj = self.pool.get('account.invoice')
            model = context.get('active_model')
            if model == 'account.move.line':
                for mvl in mvl_obj.browse(cr, uid, active_ids, context):
                    if mvl.credit > 0 and mvl.reconcile_id:
                        payment_ids.append(mvl.id)

            elif model == 'account.invoice':
                for inv in invoice_obj.browse(cr, uid, active_ids, context):
                    payment_ids.extend(
                        [mvl.id for mvl in inv.payment_ids if
                         mvl.credit > 0])

        return {id: payment_ids for id in ids}

    def _write_invoice_lines(self, cr, uid, ids, field_name, field_value, arg,
                             context):
        invl_obj = self.pool.get('account.invoice.line')
        wizard = self._get_wizard(cr, uid, ids, context)
        invoice_id = wizard.invoice_id and wizard.invoice_id.id
        for line in field_value:
            if isinstance(line, (tuple, list)):
                action = line[0]
                invl_id = line[1]
                invl_vals = line[2]
                if action == 0:    # Create record
                    invl_vals['invoice_id'] = invoice_id
                    invl_obj.create(cr, uid, invl_vals, context)
                if action == 1:  # one2many update
                    invl_obj.write(cr, uid, [invl_id], invl_vals, context)
                if action in (2, 3):    # one2many delete
                    invl_obj.unlink(cr, uid, [invl_id], context)
                if action == 4:     # Link record
                    invl_obj.write(cr, uid, [invl_id], {
                        'invoice_id': invoice_id}, context)

        return True

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################
    _columns = {
        'state': fields.selection([
            ('unrec', _('Unreconcile')),
            ('change', _('Change Lines')),
            ('rec', _('Reconcile'))], 'state'),
        'payment_ids': fields.function(
            _get_payment_ids, type='one2many', obj='account.move.line'),
        'invoice_line_ids': fields.function(
            _get_invoice_lines, fnct_inv=_write_invoice_lines, type='one2many',
            obj='account.invoice.line', method=True,
            string=_('Related invoice lines'),
            help=_('You can directly edit the invoice lines from here if '
                   'you want to change the attribution of the payment.')),
        'amount_total': fields.function(
            _get_amount_total, type='float', string=_('Payment Total'),
            readonly=True),
        'amount_computed': fields.related(
            'invoice_id', 'amount_total', type='float', string=_('Total'),
            readonly=True),

        # Invoice related fields
        'invoice_id': fields.many2one('account.invoice', 'New invoice'),
        'partner_id': fields.related('invoice_id', 'partner_id', 'id',
                                     type='integer', string='partner id'),
        'currency_id': fields.related('invoice_id', 'currency_id', 'id',
                                      type='integer', string='currency id'),
        'company_id': fields.related('invoice_id', 'company_id', 'id',
                                     type='integer', string='company id'),
        'invoice_type': fields.related('invoice_id', 'type', type='char',
                                       string='invoice type'),
        'fiscal_position': fields.related('invoice_id', 'fiscal_position',
                                          'id', type='integer',
                                          string='fiscal position'),
        'operation_valid': fields.boolean('Is operation valid'),
        'comment': fields.text(_("Comment"), help=_(
            "Explain why you changed the attribution."))
    }

    _defaults = {
        'state': 'unrec',
        'invoice_line_ids': _get_default_invl,
        'amount_total': _get_default_total,
    }

    ##########################################################################
    #                             VIEW CALLBACKS                             #
    ##########################################################################
    def unreconcile(self, cr, uid, ids, context=None):
        """ Unreconcile selected payments. """
        wizard = self._get_wizard(cr, uid, ids, context)
        invoice_lines = wizard.invoice_line_ids
        if not invoice_lines:
            raise orm.except_orm(
                _("Invalid selection"),
                _("I couldn't find any invoice to modify. Please verify "
                  "your selection."))

        # Put functional fields in context to avoid computing them several
        # times.
        pay_ids = [p.id for p in wizard.payment_ids]
        context.update({
            'payment_ids': pay_ids,
            'amount_total': wizard.amount_total,
        })

        # Unreconcile payments
        mvl_ids = list()
        for mvl in wizard.payment_ids:
            mvl_ids.extend([l.id for l in mvl.reconcile_id.line_id])
        self.pool.get('account.move.line')._remove_move_reconcile(
            cr, uid, mvl_ids, context=context)

        # Cancel paid invoices and move invoice lines to a new
        # draft invoice.
        invoice_obj = self.pool.get('account.invoice')
        invoice_line_obj = self.pool.get('account.invoice.line')
        new_invoice_id = False
        invoice_ids = list()
        wf_service = netsvc.LocalService('workflow')
        for invoice_line in invoice_lines:
            invoice = invoice_line.invoice_id
            if invoice.id not in invoice_ids:
                invoice_ids.append(invoice.id)
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
                        ('partner_id', '=', invoice.partner_id.id),
                        ('state', '=', 'draft'),
                        ('date_invoice', '=', today)], context=context)[0]

                wf_service.trg_validate(uid, 'account.invoice', invoice.id,
                                        'invoice_cancel', cr)
                invoice.write({'comment': wizard.comment or
                               'Payment attribution changed.'})
                invl_ids = [invl.id for invl in invoice.invoice_line]
                for id in invl_ids:
                    invoice_line_obj.copy(cr, uid, id, {
                        'invoice_id': new_invoice_id}, context)

        wizard.write({
            'state': 'change',
            'invoice_id': new_invoice_id})

        return self._refresh(cr, uid, wizard.id, context)

    def compute(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        wizard = self.browse(cr, uid, ids, context)
        wizard.invoice_id.button_compute(set_total=True)
        return self._refresh(cr, uid, wizard.id, context)

    def validate(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        wizard = self.browse(cr, uid, ids, context)

        # Validate the invoice
        wf_service = netsvc.LocalService('workflow')
        invoice = wizard.invoice_id
        wf_service.trg_validate(uid, 'account.invoice', invoice.id,
                                'invoice_open', cr)

        wizard.write({
            'state': 'rec',
            'operation_valid': wizard.amount_computed == wizard.amount_total})

        return self._refresh(cr, uid, wizard.id, context)

    def reconcile(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        wizard = self.browse(cr, uid, ids, context)
        invoice = wizard.invoice_id
        move_line_obj = self.pool.get('account.move.line')

        # Reconcile all related move lines
        move_line_ids = move_line_obj.search(cr, uid, [
            ('move_id', '=', invoice.move_id.id),
            ('account_id', '=', invoice.account_id.id)],
            context=context)
        move_line_ids.extend([mvl.id for mvl in wizard.payment_ids])
        move_line_obj.reconcile(cr, uid, move_line_ids, 'manual',
                                context=context)

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def close(self, cr, uid, ids, context=None):
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################
    def _get_invl_ids_from_mvl_ids(self, cr, uid, mvl_ids, context=None):
        mvl_obj = self.pool.get('account.move.line')
        invoice_obj = self.pool.get('account.invoice')
        invl_ids = list()
        for mvl in mvl_obj.browse(cr, uid, mvl_ids, context):
            # Look for credit lines
            if mvl and mvl.credit > 0 and mvl.reconcile_id:
                # Find related reconciled invoices
                invoice_ids = invoice_obj.search(cr, uid, [
                    ('move_id.line_id.reconcile_id',
                     '=', mvl.reconcile_id.id),
                    ('state', '=', 'paid'),
                    ('residual', '=', 0.0)], context=context)
                for inv in invoice_obj.browse(cr, uid, invoice_ids, context):
                    invl_ids.extend([invl.id for invl in inv.invoice_line])
        return invl_ids

    def _get_wizard(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        if ids != 0:
            return self.browse(cr, uid, ids, context)
        return False

    def _refresh(self, cr, uid, wizard_id, context=None):
        return {
            'name': _('Change attribution'),
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': wizard_id,
            'view_mode': 'form',
            'view_type': 'form',
            'context': context,
            'target': 'new',
        }
