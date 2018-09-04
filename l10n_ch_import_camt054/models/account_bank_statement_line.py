# -*- coding: utf-8 -*-
"""Add process_camt method to account.bank.statement.import."""
# © 2017 Compassion CH <http://www.compassion.ch>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import models, fields


class AccountBankStatementLine(models.Model):
    """Add process_camt method to account.bank.statement.import."""
    _inherit = 'account.bank.statement.line'

    acct_svcr_ref = fields.Char()

    def process_reconciliation(self, counterpart_aml_dicts=None,
                               payment_aml_rec=None, new_aml_dicts=None):
        counterpart_moves = super(
            AccountBankStatementLine, self).process_reconciliation(
                counterpart_aml_dicts, payment_aml_rec, new_aml_dicts)

        if hasattr(self, 'acct_svcr_ref') and self.acct_svcr_ref:
            for move_line in counterpart_moves.line_ids:
                move_line.acct_svcr_ref = self.acct_svcr_ref

        return counterpart_moves

    def _prepare_reconciliation_move_line(self, move, amount):
        data = super(AccountBankStatementLine, self).\
            _prepare_reconciliation_move_line(move, amount)
        # Add the acct svcr ref to both move line.
        data['acct_svcr_ref'] = self.acct_svcr_ref
        return data

    def camt054_reconcile(self, account_code):
        move_line_obj = self.env['account.move.line']

        move_line_list = move_line_obj.search([
            ('reconciled', '!=', 'False'),
            ('account_id.code', '=', account_code),
            ('acct_svcr_ref', '!=', None)
        ])

        list_line = dict()

        # Group each line by acct_svcr_ref
        for line in move_line_list:
            acct_svcr_ref = line.acct_svcr_ref

            # Add the acct_svcr_ref to the list if it's not already present
            if acct_svcr_ref not in list_line:
                list_line[acct_svcr_ref] = []
            # If it is already present we add the line the the list of
            # this acct_svcr_ref
            list_line[acct_svcr_ref].append(line)

        for list_acct_svcr_ref in list_line:

            credit = 0
            debit = 0
            move_line_list = move_line_obj.search([
                ('acct_svcr_ref', '=', list_acct_svcr_ref),
                ('reconciled', '!=', 'False'),
                ('account_id.code', '=', account_code)])

            # Check if credit = debit
            for line in move_line_list:
                credit += line.credit
                debit += line.debit
            if credit == debit:
                move_line_list.reconcile()
