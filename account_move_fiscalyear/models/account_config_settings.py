##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    @author: Quentin Gigon <gigon.quentin@gmail.com>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models, fields, api


class AccountConfigSettingsFiscalReport(models.TransientModel):
    _inherit = 'res.config.settings'

    move_bills_date = fields.Boolean(
        related='company_id.move_bills_date', string="Move unclosed bills to "
        "next fiscal year", default=False)

    @api.model
    def get_values(self):
        res = super().get_values()
        res['move_bills_date'] = False
        return res
