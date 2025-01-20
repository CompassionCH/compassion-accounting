from odoo import models


class AccountTax(models.Model):
    _inherit = "account.tax"

    def _get_generation_dict_from_base_line(
        self, line_vals, tax_vals, force_caba_exigibility=False
    ):
        grouping = super()._get_generation_dict_from_base_line(
            line_vals, tax_vals, force_caba_exigibility
        )
        product = line_vals.get("product")
        contract = line_vals.get("contract")
        grouping["product_id"] = (
            product.id if product and not tax_vals["use_in_tax_closing"] else False
        )
        grouping["contract_id"] = (
            contract.id if contract and not tax_vals["use_in_tax_closing"] else False
        )
        return grouping

    def _get_generation_dict_from_tax_line(self, line_vals):
        tax_grouping = super()._get_generation_dict_from_tax_line(line_vals)
        product = line_vals.get("product")
        contract = line_vals.get("contract")
        tax_grouping["product_id"] = product.id if product else False
        tax_grouping["contract_id"] = contract.id if contract else False
        return tax_grouping
