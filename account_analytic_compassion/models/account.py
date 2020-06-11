##############################################################################
#
#    Copyright (C) 2020 Compassion CH (http://www.compassion.ch)
#    @author: William Martin <wmartin@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, models
import re


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.multi
    def _check_analytic_distribution_required_msg(self):
        message = super(AccountMoveLine, self).\
            _check_analytic_distribution_required_msg()
        pattern = r'.*mutually exclusive.*'
        if message and not re.match(pattern, message, re.IGNORECASE):
            return message
        pass
