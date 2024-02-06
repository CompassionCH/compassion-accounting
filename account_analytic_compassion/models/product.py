##############################################################################
#
#    Copyright (C) 2020 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: William Martin <wmartin@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = "product.template"

    analytic_default_id = fields.Many2one(
        "account.analytic.default",
        "Analytic Default",
    )
