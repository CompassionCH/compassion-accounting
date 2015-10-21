# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from openerp import api, models, exceptions, _
from openerp.tools import mod10r, DEFAULT_SERVER_DATE_FORMAT as DF
from openerp.addons.sponsorship_compassion.model.product import \
    GIFT_CATEGORY, GIFT_NAMES, SPONSORSHIP_CATEGORY

from datetime import datetime


class bank_statement_line(models.Model):

    _inherit = 'account.bank.statement.line'

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################
    @api.model
    def get_reconciliation_proposition(self, st_line, excluded_ids=None):
        """ Never propose reconciliation when move_lines have not
            the same reference.
        """
        res = super(bank_statement_line, self).get_reconciliation_proposition(
            st_line, excluded_ids)
        filtered_res = [data for data in res if data['ref'] == st_line.ref]
        return filtered_res

    @api.model
    def get_move_lines_for_reconciliation(
            self, st_line, excluded_ids=None, str=False, offset=0, limit=None,
            count=False, additional_domain=None):
        """ Sort move lines according to Compassion criterias :
            Move line for current month at first,
            Then other move_lines, from the oldest to the newest.
        """
        # Propose up to 12 move lines for a complete year.
        if limit is not None and limit < 12:
            limit = 12

        res_asc = super(
            bank_statement_line, self).get_move_lines_for_reconciliation(
            st_line, excluded_ids, str, offset, limit, count,
            additional_domain)

        # Sort results with date (current month at first)
        res_sorted = list()
        today = datetime.today().date()
        for mv_line_dict in res_asc:
            mv_date = datetime.strptime(
                mv_line_dict['date_maturity'] or mv_line_dict['date'], DF)
            if mv_date.month == today.month and mv_date.year == today.year:
                res_sorted.insert(0, mv_line_dict)
            else:
                res_sorted.append(mv_line_dict)

        # Put matching references at first
        res_sorted = sorted(
            res_sorted, key=lambda mvl_data: mvl_data['ref'] == st_line.ref,
            reverse=True)
        return res_sorted

    @api.one
    def process_reconciliation(self, mv_line_dicts):
        """ Create invoice if product_id is set in move_lines
        to be created. """
        partner_invoices = dict()
        partner_inv_data = dict()
        old_counterparts = dict()
        index = 0
        for mv_line_dict in mv_line_dicts:
            partner_id = self.partner_id.id
            if mv_line_dict.get('product_id'):
                # Create invoice
                mv_line_dict['index'] = index
                if partner_id in partner_inv_data:
                    partner_inv_data[partner_id].append(mv_line_dict)
                else:
                    partner_inv_data[partner_id] = [mv_line_dict]
            mv_line_id = mv_line_dict.get('counterpart_move_line_id')
            if mv_line_id:
                # An invoice exists for that partner, we will use it
                # to put leftover amount in it, if any exists.
                invoice = self.env['account.move.line'].browse(
                    mv_line_id).invoice
                if invoice and invoice.period_id.state != 'done':
                    partner_invoices[partner_id] = invoice
                    old_counterparts[invoice.id] = mv_line_id
            index += 1

        # Create invoice and update move_line_dicts to reconcile them.
        for partner_id, partner_data in partner_inv_data.iteritems():
            invoice = partner_invoices.get(partner_id)
            new_counterpart = self._create_invoice_from_mv_lines(
                partner_data, invoice)
            for data in partner_data:
                index = data['index']
                mv_line_dicts[index] = data
                del mv_line_dicts[index]['index']
            if invoice:
                old_counterpart = old_counterparts[invoice.id]
                for mv_line_dict in mv_line_dicts:
                    counterpart = mv_line_dict.get('counterpart_move_line_id')
                    if counterpart == old_counterpart:
                        mv_line_dict[
                            'counterpart_move_line_id'] = new_counterpart

        super(bank_statement_line, self).process_reconciliation(mv_line_dicts)

    @api.model
    def product_id_changed(self, product_id):
        """ Called when a product is selected for counterpart.
        Returns useful info to fullfill other fields.
        """
        analytic_id = self.env['account.analytic.default'].account_get(
            product_id).analytic_id.id
        account_id = self.env['product.product'].browse(
            product_id).property_account_income.id
        return {
            'analytic_id': analytic_id,
            'account_id': account_id
        }

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################
    def _create_invoice_from_mv_lines(self, mv_line_dicts, invoice=None):
        # Get the attached recurring invoicer
        invoicer = self.statement_id.recurring_invoicer_id
        if not invoicer:
            invoicer_obj = self.env['recurring.invoicer']
            invoicer = invoicer_obj.create({'source': self._name})
            self.statement_id.write({'recurring_invoicer_id': invoicer.id})

        # Generate a unique bvr_reference
        ref = self.ref
        if ref and len(ref) > 27:
            ref = mod10r(ref[:26])
        elif len(ref) < 26:
            ref = mod10r((self.date.replace('-', '') + str(
                self.statement_id.id) + str(self.id)).ljust(26, '0'))

        if invoice:
            invoice.action_cancel()
            invoice.action_cancel_draft()
            invoice.write({'recurring_invoicer_id': invoicer.id})

        else:
            # Lookup for an existing open invoice matching the criterias
            invoices = self._find_open_invoice(mv_line_dicts)
            if invoices:
                # Get the bvr reference of the invoice or set it
                invoice = invoices[0]
                invoice.write({'recurring_invoicer_id': invoicer.id})
                if invoice.bvr_reference and not self.ref:
                    ref = invoice.bvr_reference
                else:
                    invoice.write({'bvr_reference': ref})
                self.write({
                    'ref': ref,
                    'invoice_id': invoice.id})
                return True

            # Setup a new invoice if no existing invoice is found
            journal_id = self.env['account.journal'].search(
                [('type', '=', 'sale')], limit=1).id
            if self.journal_id.code == 'BVR':
                payment_term_id = self.env.ref(
                    'contract_compassion.payment_term_bvr').id
            else:
                payment_term_id = self.env.ref(
                    'contract_compassion.payment_term_virement').id
            inv_data = {
                'account_id': self.partner_id.property_account_receivable.id,
                'type': 'out_invoice',
                'partner_id': self.partner_id.id,
                'journal_id': journal_id,
                'date_invoice': self.date,
                'payment_term': payment_term_id,
                'bvr_reference': ref,
                'recurring_invoicer_id': invoicer.id,
                'currency_id': self.statement_id.currency.id,
            }
            invoice = self.env['account.invoice'].create(inv_data)

        for mv_line_dict in mv_line_dicts:
            product = self.env['product.product'].browse(
                mv_line_dict['product_id'])
            sponsorship_id = mv_line_dict.get('sponsorship_id')
            if not sponsorship_id:
                related_contracts = invoice.mapped('invoice_line.contract_id')
                if related_contracts:
                    sponsorship_id = related_contracts[0].id
            contract = self.env['recurring.contract'].browse(sponsorship_id)
            if product.name == GIFT_NAMES[0] and contract and \
                    contract.child_id and contract.child_id.birthdate:
                invoice.date_invoice = self.env[
                    'generate.gift.wizard'].compute_date_birthday_invoice(
                    contract.child_id.birthdate, self.date)

            amount = mv_line_dict['credit']
            inv_line_data = {
                'name': self.name,
                'account_id': product.property_account_income.id,
                'price_unit': amount,
                'price_subtotal': amount,
                'contract_id': contract.id,
                'user_id': mv_line_dict.get('user_id'),
                'quantity': 1,
                'uos_id': False,
                'product_id': product.id,
                'partner_id': self.partner_id.id,
                'invoice_id': invoice.id,
                'account_analytic_id': mv_line_dict.get(
                    'analytic_account_id',
                    self.env['account.analytic.default'].account_get(
                        product.id, self.partner_id.id).analytic_id.id)
            }

            if product.categ_name in (
                    GIFT_CATEGORY, SPONSORSHIP_CATEGORY) and not contract:
                raise exceptions.Warning(_('A field is required'),
                                         _('Add a Sponsorship'))

            self.env['account.invoice.line'].create(inv_line_data)

        invoice.button_compute()
        invoice.signal_workflow('invoice_open')
        self.ref = ref

        # Update move_lines data
        counterpart_id = invoice.move_id.line_id.filtered(
            lambda ml: ml.debit > 0).id
        for mv_line_dict in mv_line_dicts:
            mv_line_dict['counterpart_move_line_id'] = counterpart_id
            if 'sponsorship_id' in mv_line_dict:
                del mv_line_dict['sponsorship_id']
        return counterpart_id

    def _find_open_invoice(self, mv_line_dicts):
        """ Find an open invoice that matches the statement line and which
        could be reconciled with. """
        invoice_line_obj = self.env['account.invoice.line']
        inv_lines = invoice_line_obj
        for mv_line_dict in mv_line_dicts:
            amount = mv_line_dict['credit']
            inv_lines |= invoice_line_obj.search([
                ('partner_id', '=', mv_line_dict.get('partner_id')),
                ('state', 'in', ('open', 'draft')),
                ('product_id', '=', mv_line_dict.get('product_id')),
                ('price_subtotal', '=', amount)])

        return inv_lines.mapped('invoice_id').filtered(
            lambda i: i.amount_total == self.amount)
