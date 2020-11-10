##############################################################################
#
#    Copyright (C) 2020 Compassion CH (http://www.compassion.ch)
#    @author: David Wulliamoz <dwulliamoz@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models, fields, api

class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    @api.model
    def create_exchange_rate_entry(self, aml_to_fix, move):
        exchange_analytic_tag_id = self.env['ir.config_parameter'].\
            search([('key', '=', 'account_analytic_compassion.analytic_tag_id')]).value
        return super(AccountPartialReconcile, self.with_context(
            default_analytic_tag_ids=[
                (6, 0, [exchange_analytic_tag_id])
            ])).create_exchange_rate_entry( aml_to_fix, move)
