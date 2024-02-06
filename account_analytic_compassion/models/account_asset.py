##############################################################################
#
#    Copyright (C) 2020 Compassion CH (http://www.compassion.ch)
#    @author: William Martin <wmartin@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models, fields


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    # Many2many field to account.analytic.tag table
    analytic_tag_ids = fields.Many2many(
        comodel_name='account.analytic.tag',
        string='Analytic Tags',
    )


class AccountAssetLine(models.Model):
    _inherit = 'account.asset.line'

    # override of parent method _setup_move_line_data
    # inherited from object AccountAssetLine
    # at account-financial-tools/account_asset_management/models/account_asset_line.py
    def _setup_move_line_data(self, depreciation_date, account, ml_type, move):
        move_line_data = super()._setup_move_line_data(depreciation_date,
                                                       account,
                                                       ml_type,
                                                       move)
        move_line_data['analytic_tag_ids'] = [
            (6, 0, self.asset_id.analytic_tag_ids.ids)]
        return move_line_data
