import logging
from collections import defaultdict

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

        currency = partial.company_currency_id or self.company_currency_id
        reconciled_lines = partial.credit_move_id + partial.debit_move_id
        # The generated move lines have the same name as the move
        offbalance_lines = reconciled_lines.move_id.line_ids.filtered(
            "is_off_balance_generated"
        )
        if not offbalance_lines:
            # In case of debit orders we also fetch the banking entry reconciled
            reconciled_lines += (
                reconciled_lines.move_id.line_ids.full_reconcile_id.reconciled_line_ids
            )
            offbalance_lines = reconciled_lines.move_id.line_ids.filtered(
                "is_off_balance_generated"
            )
        lines_to_unlink = self.env["account.move.line"]
        if offbalance_lines and currency:
            adjustment_map = self._prepare_offbalance_partial_delta(partial, currency)
            if adjustment_map:
                lines_to_unlink = self._apply_offbalance_partial_delta(
                    offbalance_lines, adjustment_map, currency
                )
        if lines_to_unlink:
            lines_to_unlink.remove_move_reconcile()
            lines_to_unlink.with_context(
                dynamic_unlink=True, force_delete=True
            ).unlink()

        # Remove payment lines
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

        return super().js_remove_outstanding_partial(partial_id)

    def _prepare_offbalance_partial_delta(self, partial, currency):
        """Prepares a map of adjustments to be made to on-balance
        :return: A map of (account_id, product_id) to adjustment amount"""
        invoice_line_reconciled = self.env["account.move.line"]
        for line in (partial.debit_move_id, partial.credit_move_id):
            if line.move_type in ("out_invoice", "out_refund"):
                invoice_line_reconciled = line
                break
        if not invoice_line_reconciled or not currency:
            return {}
        invoice_total = abs(invoice_line_reconciled.balance)
        if currency.is_zero(invoice_total):
            return {}
        delta_map = defaultdict(float)
        for line in invoice_line_reconciled.move_id.invoice_line_ids.filtered(
            lambda inv_line: inv_line.account_id.on_balance_account_id
        ):
            removal_amount = currency.round(line.balance)
            if currency.is_zero(removal_amount):
                continue
            key = (
                line.account_id.on_balance_account_id.id,
                line.product_id.id or False,
            )
            delta_map[key] += -removal_amount
        return delta_map

    def _apply_offbalance_partial_delta(self, offbalance_lines, delta_map, currency):
        lines_to_delete = self.env["account.move.line"]
        if not delta_map:
            return lines_to_delete
        asset_lines = offbalance_lines.filtered(
            lambda line: line.account_id == line.company_id.off_balance_asset_account_id
        )
        onbalance_lines = offbalance_lines - asset_lines
        lines_by_key = {}
        for line in onbalance_lines:
            key = (line.account_id.id, line.product_id.id or False)
            lines_by_key.setdefault(key, self.env["account.move.line"])
            lines_by_key[key] |= line
        applied_total = 0.0
        for key, delta in delta_map.items():
            if currency.is_zero(delta):
                continue
            lines = lines_by_key.get(key)
            if not lines:
                _logger.warning(
                    "Off-balance cleanup skipped for account %s product %s on move %s",
                    key[0],
                    key[1],
                    ", ".join(onbalance_lines.mapped("move_id.name")),
                )
                continue
            zero_lines, remaining = self._apply_delta_to_lines(lines, delta, currency)
            lines_to_delete |= zero_lines
            applied_delta = delta - remaining
            applied_total += applied_delta
            if not currency.is_zero(remaining):
                _logger.warning(
                    "Incomplete adjustment for account %s product %s, remaining %.2f",
                    key[0],
                    key[1],
                    remaining,
                )
        if currency.is_zero(applied_total):
            return lines_to_delete
        asset_delta = -applied_total
        zero_assets, remaining_asset = self._apply_delta_to_lines(
            asset_lines, asset_delta, currency
        )
        lines_to_delete |= zero_assets
        if not currency.is_zero(remaining_asset):
            _logger.warning(
                "Asset adjustment left remainder %.2f on move(s) %s",
                remaining_asset,
                ", ".join(asset_lines.mapped("move_id.name")),
            )
        return lines_to_delete

    def _apply_delta_to_lines(self, lines, delta, currency):
        zero_lines = self.env["account.move.line"]
        if not lines or currency.is_zero(delta):
            return zero_lines, delta
        remaining = delta
        for line in lines.sorted(key=lambda mvl: abs(mvl.balance), reverse=True):
            if currency.is_zero(remaining):
                break
            balance = currency.round(line.balance)
            if currency.is_zero(balance):
                zero_lines |= line
                continue
            if balance * remaining > 0:
                continue
            available = abs(balance)
            portion = min(available, abs(remaining))
            adjustment = portion if remaining > 0 else -portion
            new_balance = balance + adjustment
            self._write_line_balance(line, new_balance)
            if currency.is_zero(new_balance):
                zero_lines |= line
            remaining -= adjustment
        return zero_lines, remaining

    def _write_line_balance(self, line, new_balance):
        currency = line.company_currency_id
        rounded = currency.round(new_balance)
        debit = rounded if rounded > 0 else 0.0
        credit = -rounded if rounded < 0 else 0.0
        line.with_context(check_move_validity=False).write(
            {
                "balance": rounded,
                "debit": debit,
                "credit": credit,
            }
        )
