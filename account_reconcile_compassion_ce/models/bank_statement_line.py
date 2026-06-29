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
        if self.manual_product_id:
            self.manual_account_id = (
                self.manual_product_id.property_account_income_id.id
            )

    @api.onchange("manual_contract_id")
    def on_change_manual_contract_id(self):
        # Make sure the reconcile data is updated when the contract changes
        self._onchange_manual_reconcile_vals()

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
        vals["product_id"] = line.get("product_id")[0] if line.get("product_id") else False
        vals["contract_id"] = line.get("contract_id")[0] if line.get("contract_id") else False
        return vals

    def _check_line_changed(self, line):
        res = super()._check_line_changed(line)
        return (
            res
            or self.manual_product_id.id != line.get("product_id", (False,))[0]
            or self.manual_contract_id.id != line.get("contract_id", (False,))[0]
        )
