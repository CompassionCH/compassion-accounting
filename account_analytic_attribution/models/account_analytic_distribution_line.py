# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################
from openerp import models, fields


class AccountDistributionLine(models.Model):
    """
    Attribution are used for 2 purposes:
    1. Select automatically an analytic account when selecting a product
       on invoices (type attribution)
    2. Dispatch analytic lines into other analytic accounts
       (type distribution)
    """
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
