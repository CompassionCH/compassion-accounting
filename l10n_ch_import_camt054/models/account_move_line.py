# -*- coding: utf-8 -*-
# © 2017 Compassion CH <http://www.compassion.ch>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import models, fields


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    # The new field would be use for an automatic reconciliation.
    acct_svcr_ref = fields.Char()
