import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    manual_product_id = fields.Many2one(
        comodel_name="product.product",
        check_company=True,
        store=False,
        default=False,
        prefetch=False,
    )
    manual_contract_id = fields.Many2one(
        comodel_name="recurring.contract",
        check_company=True,
        store=False,
        default=False,
        prefetch=False,
    )

    @api.onchange("manual_product_id")
    def on_change_manual_product_id(self):
        # Only auto-fill the account when no account is already set.
        # When loading from a reconcile model line, manual_account_id is already
        # set by _process_manual_reconcile_from_line, so we must not override it.
        if self.manual_product_id and not self.manual_account_id:
            self.manual_account_id = (
                self.manual_product_id.property_account_income_id.id
            )

    @api.onchange("manual_contract_id")
    def on_change_manual_contract_id(self):
        # Make sure the reconcile data is updated when the contract changes
        self._onchange_manual_reconcile_vals()

    def _process_manual_reconcile_from_line(self, line):
        """Also restore manual_product_id and manual_contract_id from line data.

        The base implementation sets manual_account_id, manual_amount, etc. but
        not the custom fields added by this module. Without this override,
        _check_line_changed always detects a product/contract mismatch and
        _onchange_manual_reconcile_vals clears the product from the line dict.
        """
        res = super()._process_manual_reconcile_from_line(line)
        product_id = line.get("product_id")
        if isinstance(product_id, list | tuple):
            product_id = product_id[0]
        contract_id = line.get("contract_id")
        if isinstance(contract_id, list | tuple):
            contract_id = contract_id[0]
        self.manual_product_id = product_id or False
        self.manual_contract_id = contract_id or False
        return res

    def _get_manual_reconcile_vals(self):
        vals = super()._get_manual_reconcile_vals()
        vals["product_id"] = (
            self.manual_product_id.id,
            self.manual_product_id.display_name,
        )
        vals["contract_id"] = (
            self.manual_contract_id.id,
            self.manual_contract_id.display_name,
        )
        return vals

    def _reconcile_move_line_vals(self, line, move_id=False):
        vals = super()._reconcile_move_line_vals(line, move_id=move_id)
        product_id = line.get("product_id")
        if isinstance(product_id, list | tuple):
            product_id = product_id[0]
        contract_id = line.get("contract_id")
        if isinstance(contract_id, list | tuple):
            contract_id = contract_id[0]
        vals["product_id"] = product_id or False
        vals["contract_id"] = contract_id or False
        return vals

    def _check_line_changed(self, line):
        res = super()._check_line_changed(line)
        product_id = line.get("product_id", (False,))
        if isinstance(product_id, int):
            product_id = (product_id,)
        contract_id = line.get("contract_id", (False,))
        if isinstance(contract_id, int):
            contract_id = (contract_id,)
        return (
            res
            or self.manual_product_id.id != product_id[0]
            or self.manual_contract_id.id != contract_id[0]
        )
