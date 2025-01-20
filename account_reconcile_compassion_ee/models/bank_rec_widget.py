from odoo import models


class BankRecWidget(models.Model):
    _inherit = "bank.rec.widget"

    def _convert_to_tax_base_line_dict(self, line):
        tax_base_line_dict = super()._convert_to_tax_base_line_dict(line)
        tax_base_line_dict["product"] = line.product_id
        tax_base_line_dict["contract"] = line.contract_id
        return tax_base_line_dict

    def _convert_to_tax_line_dict(self, line):
        tax_line_dict = super()._convert_to_tax_line_dict(line)
        tax_line_dict["product"] = line.product_id
        tax_line_dict["contract"] = line.contract_id
        return tax_line_dict

    def _lines_prepare_tax_line(self, tax_line_vals):
        tax_line_data = super()._lines_prepare_tax_line(tax_line_vals)
        tax_line_data["product_id"] = tax_line_vals.get("product_id", False)
        tax_line_data["contract_id"] = tax_line_vals.get("contract_id", False)
        return tax_line_data

    def _line_value_changed_product_id(self, line):
        self.ensure_one()
        if line.product_id and line.credit:
            line.account_id = line.product_id.property_account_income_id
        elif line.product_id and line.debit:
            line.account_id = line.product_id.property_account_expense_id
        self._lines_turn_auto_balance_into_manual_line(line)

        if line.flag != "tax_line":
            self._lines_recompute_taxes()

    def _line_value_changed_contract_id(self, line):
        self.ensure_one()
        self._lines_turn_auto_balance_into_manual_line(line)

        if line.flag != "tax_line":
            self._lines_recompute_taxes()
