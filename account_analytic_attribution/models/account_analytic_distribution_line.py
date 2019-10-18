##############################################################################
#
#    Copyright (C) 2015-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models, fields


class AccountDistributionLine(models.Model):
    _name = "account.analytic.distribution.line"
    _description = "Analytic Distribution Line"

    attribution_id = fields.Many2one(
        'account.analytic.attribution', 'Analytic Attribution',
        required=True, ondelete='cascade'
    )
    rate = fields.Float()
    account_analytic_id = fields.Many2one(
        'account.analytic.account', 'Analytic Account', required=True
    )
