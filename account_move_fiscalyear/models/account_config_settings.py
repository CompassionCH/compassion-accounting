# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    @author: Quentin Gigon <gigon.quentin@gmail.com>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models, fields


class AccountConfigSettingsFiscalReport(models.TransientModel):
    _inherit = 'account.config.settings'

    move_bills_date = fields.Boolean(
        related='company_id.move_bills_date', string="Move unclosed bills to "
        "next fiscal year", default=False)
