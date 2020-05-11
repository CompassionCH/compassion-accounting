"""Add process_camt method to account.bank.statement.import."""
# © 2017 Compassion CH <http://www.compassion.ch>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import models, fields, release


class AccountBankStatementLine(models.Model):
    """Add process_camt method to account.bank.statement.import."""
    _inherit = 'account.bank.statement.line'

    acct_svcr_ref = fields.Char()

    def process_reconciliation(self, counterpart_aml_dicts=None,
                               payment_aml_rec=None, new_aml_dicts=None):
        counterpart_moves = super().process_reconciliation(
                counterpart_aml_dicts, payment_aml_rec, new_aml_dicts)

        if hasattr(self, 'acct_svcr_ref') and self.acct_svcr_ref:
            for move_line in counterpart_moves.line_ids:
                move_line.acct_svcr_ref = self.acct_svcr_ref

        return counterpart_moves

    def _prepare_reconciliation_move_line(self, move, amount):
        data = super()._prepare_reconciliation_move_line(move, amount)
        # Add the acct svcr ref to both move line.
        data['acct_svcr_ref'] = self.acct_svcr_ref
        return data

    def camt054_reconcile(self, account_code):
        move_line_obj = self.env['account.move.line']

        all_move_lines = move_line_obj.search([
            ('reconciled', '=', False),
            ('account_id.code', '=', account_code),
            ('acct_svcr_ref', '!=', False)
        ])

        # Group each line by acct_svcr_ref
        for acct_svcr_ref in set(all_move_lines.mapped('acct_svcr_ref')):
            move_lines = all_move_lines.filtered(
                lambda x: x.acct_svcr_ref == acct_svcr_ref)
            if len(move_lines) > 1 and sum(move_lines.mapped('debit')) == \
                    sum(move_lines.mapped('credit')):
                # the reconcile function makes use of the recursive
                # auto_reconcile function. This function is slow due to calls
                # to _compute_partial_lines. This was improved in Odoo v12
                # (see d3d26120614139fd7d7e888bd66d21de5158a034).
                # We therefore skip the call when move_lines is too big.
                if float(release.version) >= 12 or len(move_lines) < 500:
                    move_lines.reconcile()
