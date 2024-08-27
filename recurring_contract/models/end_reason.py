##############################################################################
#
#    Copyright (C) 2019 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import fields, models


class EndReason(models.Model):
    _name = "recurring.contract.end.reason"
    _description = "Recurring contract end reason"

    name = fields.Char(translate=True, required=True)
