##############################################################################
#
#    Copyright (C) 2016-2022 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import models, fields, api

from odoo.addons.recurring_contract.models.contract_group import ContractGroup


class MandateStaffNotifSettings(models.TransientModel):
    """ Settings configuration for any Notifications."""
    _inherit = "res.config.settings"

    # offset to know if we should generate current month or not
    do_generate_curr_month = fields.Boolean(
        string="Generate current month ?",
        help="Define if the invoices should generate the current month by default or the next month."
             "Ticked means we generate the current month and next month by default",
        default=True,
    )
    # Day to know when we should stop generating invoices for a specific contract group on a contract creation
    inv_block_day = fields.Selection(
        selection="_day_selection",
        string="Invoices Blocked Day",
        help="If set, contracts created after this day will set their first invoice one month after. "
             "Contracts terminated after this day will cancel paid invoices one month after.",
        default="15",
    )

    def _day_selection(self):
        return ContractGroup.day_selection()

    @api.model
    def get_values(self):
        res = super().get_values()
        res["inv_block_day"] = self.get_param_multi_company("recurring_contract.invoice_block_day")
        res["do_generate_curr_month"] = self.get_param_multi_company("recurring_contract.do_generate_curr_month")
        return res

    def set_values(self):
        self._set_param_multi_company("recurring_contract.invoice_block_day", self.inv_block_day)
        self._set_param_multi_company("recurring_contract.do_generate_curr_month", str(self.do_generate_curr_month))
        super().set_values()

    def get_param_multi_company(self, par_name):
        param_string = f"{par_name}_{self.env.company.id}"
        return self.env["ir.config_parameter"].sudo().get_param(param_string, False)

    def _set_param_multi_company(self, par_name, par_val):
        self.env["ir.config_parameter"].set_param(
            f"{par_name}_{self.env.company.id}", par_val
        )
