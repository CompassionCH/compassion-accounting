##############################################################################
#
#    Copyright (C) 2018-2020 Compassion CH (http://www.compassion.ch)
#    @author: Quentin Gigon <gigon.quentin@gmail.com>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import fields, models


class AccountUpdateLockDate(models.TransientModel):
    _inherit = "account.update.lock_date"

    move_bills_date = fields.Boolean(
        related="company_id.move_bills_date",
        string="Move unclosed bills to next fiscal year",
        readonly=False,
    )
