##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, models, fields
import logging

logger = logging.getLogger(__name__)


class Journal(models.Model):
    """ Add completion rules to journals """
    _inherit = 'account.journal'

    completion_rules = fields.Many2many('account.statement.completion.rule', readonly=False)


class StatementCompletionRule(models.Model):
    """ Rules to complete account bank statements."""
    _name = "account.statement.completion.rule"
    _description = 'Account Statement Completion Rule'

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################

    sequence = fields.Integer('Sequence',
                              help="Lower means parsed first.")
    name = fields.Char('Name', size=128)
    journal_ids = fields.Many2many(
        'account.journal',
        string='Related statement journal', readonly=False)
    function_to_call = fields.Selection([
        ('get_from_amount', 'Compassion: From line amount '
         '(based on the amount of the supplier invoice)'),
        ('get_from_move_line_ref', 'Compassion: From line reference '
         '(based on previous move_line references)'),
        ('get_from_payment_line', 'From payment line reference')
        ], 'Method')

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################

    @api.multi
    def auto_complete(self, stmts_vals, stmt_line):
        """This method will execute all related rules, in their sequence order,
        to retrieve all the values returned by the first rules that will match.
        :param stmts_vals: dict with bank statement values
        :param dict stmt_line: dict with statement line values
        :return:
            A dict of values for the bank statement line or {}
           {'partner_id': value,
            'account_id': value,
            ...}
        """
        for rule in self.sorted(key=lambda r: r.sequence):
            method = getattr(self, rule.function_to_call)
            result = method(stmts_vals, stmt_line)
            if result:
                return result
        return dict()

    def get_from_amount(self, stmts_vals, st_line):
        """ If line amount match an open supplier invoice,
            update partner and account. """
        amount = st_line['amount']
        res = {}
        # We check only for debit entries
        if amount < 0:
            invoice_obj = self.env['account.invoice']
            invoices = invoice_obj.search(
                [('type', '=', 'in_invoice'), ('state', '=', 'open'),
                 ('amount_total', '=', abs(amount))])
            res = {}
            if invoices:
                if len(invoices) == 1:
                    partner = invoices.partner_id
                    res['partner_id'] = partner.commercial_partner_id.id
                else:
                    partner = invoices[0].partner_id
                    for invoice in invoices:
                        if invoice.partner_id.id != partner.id:
                            logger.warning(
                                f"Line named {st_line['name']} (Ref:{st_line['ref']})"
                                f" was matched by "
                                'more than one invoice while looking on open'
                                ' supplier invoices')
                    res['partner_id'] = partner.commercial_partner_id.id
        return res

    def get_from_move_line_ref(self, stmts_vals, st_line):
        ''' Update partner if same reference is found '''
        ref = st_line.get('ref')
        res = dict()
        if not ref:
            return res
        partner = None

        # Search move lines
        move_line_obj = self.env['account.move.line']
        move_lines = move_line_obj.search(
            [('ref', '=', ref), ('partner_id', '!=', None)])
        if move_lines:
            partner = move_lines[0].partner_id

        if partner:
            res['partner_id'] = partner.commercial_partner_id.id

        return res

    def get_from_payment_line(self, stmt_vals, st_line):
        """ Search in account.payment.line """
        ref = st_line.get('ref')
        res = dict()
        if not ref:
            return res

        payment_line = self.env['bank.payment.line'].search([
            ('name', '=', ref)
        ], limit=1, order='date desc')
        if payment_line:
            res['partner_id'] = payment_line.partner_id.\
                commercial_partner_id.id
        return res
