from odoo import api, fields, models


class BankRecWidgetLine(models.Model):
    _inherit = "bank.rec.widget.line"

    product_id = fields.Many2one(
        comodel_name="product.product",
        compute="_compute_product_id",
        store=True,
        readonly=False,
        domain="[('company_id', 'in', [False, company_id]),"
        "('property_account_income_id.is_off_balance', '=', False),"
        "('property_account_expense_id.is_off_balance', '=', False)]",
    )
    contract_id = fields.Many2one(
        comodel_name="recurring.contract",
        compute="_compute_contract_id",
        store=True,
        readonly=False,
        domain="[('partner_id', '=', partner_id)]",
    )

    @api.depends("source_aml_id")
    def _compute_product_id(self):
        for line in self:
            if line.flag == "aml":
                line.product_id = line.source_aml_id.product_id
            else:
                line.product_id = line.product_id

    @api.depends("source_aml_id")
    def _compute_contract_id(self):
        for line in self:
            if line.flag == "aml":
                line.contract_id = line.source_aml_id.contract_id
            else:
                line.contract_id = line.contract_id

    def _get_aml_values(self, **kwargs):
        return super()._get_aml_values(
            **kwargs,
            product_id=self.product_id.id,
            contract_id=self.contract_id.id,
        )
