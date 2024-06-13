##############################################################################
#
#    Copyright (C) 2014-today Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: David Wulliamoz <dwulliamoz@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, fields, models


class OffBalanceAccountConfigSettings(models.TransientModel):
    """
    Add the possibility to define an off balance asset account
    and off balance receivable account
    """

    _inherit = "res.config.settings"

    account_offbalance_receivable = fields.Many2one("account.account", readonly=False)
    account_offbalance_asset = fields.Many2one("account.account", readonly=False)

    @api.model
    def get_values(self):
        res = super().get_values()
        company_id = self.env.company.id
        config = self.env["ir.config_parameter"].sudo()
        res["account_offbalance_receivable"] = int(
            config.get_param(f"account_offbalance_receivable_{company_id}", default="0")
        )
        res["account_offbalance_asset"] = int(
            config.get_param(f"account_offbalance_asset_{company_id}", default="0")
        )
        return res

    @api.model
    def set_values(self):
        company_id = self.env.company.id
        self.env["ir.config_parameter"].set_param(
            f"account_offbalance_receivable_{company_id}",
            self.account_offbalance_receivable.id,
        )
        self.env["ir.config_parameter"].set_param(
            f"account_offbalance_asset_{company_id}", self.account_offbalance_asset.id
        )
        super().set_values()
