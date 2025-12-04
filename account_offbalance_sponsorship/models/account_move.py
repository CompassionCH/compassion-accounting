import logging

from odoo import models

_logger = logging.getLogger(__name__)


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

        # 1. Remove all off-balance adjustments linked to the invoice
        generated_lines = self.line_ids.mapped("on_balance_line_ids")
        asset_lines = generated_lines.mapped("off_balance_line_ids").filtered(
            "is_off_balance_generated"
        )
        (generated_lines + asset_lines).with_context(
            dynamic_unlink=True, force_delete=True
        ).unlink()

        # 2. Remove payment lines to make the invoice payable again
        reconciled_lines = partial.credit_move_id + partial.debit_move_id
        payment_lines = self.env["account.payment.line"].search(
            [("move_line_id", "in", reconciled_lines.ids)]
        )
        if payment_lines:
            payment_lines.mapped("payment_ids").action_cancel()
            payment_lines.unlink()
            # Assign the banking line in the receivable/payable account
            reconciled_lines.filtered("statement_line_id").write(
                {"account_id": self.partner_id.property_account_receivable_id.id}
            )
        partial = self.env["account.partial.reconcile"].browse(partial_id)
        if not partial.exists():
            return True

        # 3. Do the unreconciliation
        res = super().js_remove_outstanding_partial(partial_id)

        # 4. Regenerate off-balance lines in case they are other partials linked to them
        all_reconciled_lines = (
            self.line_ids
            + self.mapped("line_ids.matched_debit_ids.debit_move_id")
            + self.mapped("line_ids.matched_credit_ids.credit_move_id")
        )
        if all_reconciled_lines:
            all_reconciled_lines._register_off_balance_income()
        return res

    def _compute_invoice_distribution_ratio(self, available_income):
        """
        Return the ratio of the invoice that can be covered by the remaining income.
        """
        self.ensure_one()
        if not self.amount_total:
            return 0.0
        if self.payment_state == "paid":
            paid_ratio = (self.amount_total - self.amount_residual) / self.amount_total
            return min(max(paid_ratio, 0.0), 1.0)
        return min(max(available_income / self.amount_total, 0.0), 1.0)
