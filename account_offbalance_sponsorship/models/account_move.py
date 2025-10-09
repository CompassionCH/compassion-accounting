from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def js_remove_outstanding_partial(self, partial_id):
        """Called by the 'payment' widget to remove a reconciled
         entry from the current invoice.

        :param partial_id: The id of an existing partial
         reconciliation linked to the current invoice.
        """

        self.ensure_one()
        partial = self.env["account.partial.reconcile"].browse(partial_id)

        if not partial:
            return False

        reconciled_lines = partial.credit_move_id + partial.debit_move_id
        # The generated move lines have the same name as the move
        move_lines_to_unlink = reconciled_lines.move_id.line_ids.filtered(
            "is_off_balance_generated"
        )
        if not move_lines_to_unlink:
            # In case of debit orders we also fetch the banking entry reconciled
            reconciled_lines += (
                reconciled_lines.move_id.line_ids.full_reconcile_id.reconciled_line_ids
            )
            move_lines_to_unlink = reconciled_lines.move_id.line_ids.filtered(
                "is_off_balance_generated"
            )
        if move_lines_to_unlink:
            # Check if moves will still be balanced after unlink
            moves_dict = {
                move: move_lines_to_unlink.filtered(
                    lambda line, m=move: line.move_id == m
                )
                for move in move_lines_to_unlink.mapped("move_id")
            }
            for move in moves_dict.keys():
                remaining_lines = move.line_ids - move_lines_to_unlink.filtered(
                    lambda line, m=move: line.move_id == m
                )
                total_debit = sum(remaining_lines.mapped("debit"))
                total_credit = sum(remaining_lines.mapped("credit"))
                if not move.currency_id.is_zero(total_debit - total_credit):
                    move_lines_to_unlink -= moves_dict[move]

        if move_lines_to_unlink:
            move_lines_to_unlink.remove_move_reconcile()
            move_lines_to_unlink.with_context(
                dynamic_unlink=True, force_delete=True
            ).unlink()

        # Undo reconciliation for the statement lines
        st_lines = self.statement_line_ids
        for line in st_lines:
            line.action_undo_reconciliation()

        partial = self.env["account.partial.reconcile"].browse(partial_id)
        if not partial.exists():
            return True

        return super().js_remove_outstanding_partial(partial_id)
