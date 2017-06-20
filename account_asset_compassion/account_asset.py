# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from odoo import api, fields, models


class asset_category(models.Model):
    _inherit = 'account.asset.category'

    analytics_id = fields.Many2one('account.analytic.plan.instance',
                                   'Analytic Distribution')


class account_asset_depreciation_line(models.Model):
    _inherit = 'account.asset.depreciation.line'

    @api.model
    def _setup_move_line_data(self, depreciation_line, depreciation_date,
                              period_ids, account_id, type, move_id):
        """ Add analytic distribution to move_line """
        move_line_data = super(account_asset_depreciation_line,
                               self)._setup_move_line_data(
            depreciation_line, depreciation_date, period_ids, account_id,
            type, move_id)
        if type == 'expense':
            move_line_data.update({
                'analytics_id':
                depreciation_line.asset_id.category_id.analytics_id.id})
        return move_line_data


class asset(models.Model):
    _inherit = 'account.asset.asset'

    @api.multi
    def close_old_asset(self):
        for asset in self:
            asset.with_context(asset_validate_from_write=True).write({
                # Triggers the computation of residual value
                'purchase_value': asset.purchase_value,
                'state': 'close'
                })

        return True
