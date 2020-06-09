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
        string='Analytic Tag',
    )


class AccountAssetLine(models.Model):
    _inherit = 'account.asset.line'

    # override of parent method _setup_move_line_data
    # inherited from object AccountAssetLine
    # at account-financial-tools/account_asset_management/models/account_asset_line.py
    def _setup_move_line_data(self, depreciation_date, account, ml_type, move):
        asset = self.asset_id
        amount = self.amount
        analytic_id = False
        if ml_type == 'depreciation':
            debit = amount < 0 and -amount or 0.0
            credit = amount > 0 and amount or 0.0
        elif ml_type == 'expense':
            debit = amount > 0 and amount or 0.0
            credit = amount < 0 and -amount or 0.0
            analytic_id = asset.account_analytic_id.id
        move_line_data = {
            'name': asset.name,
            'ref': self.name,
            'move_id': move.id,
            'account_id': account.id,
            'credit': credit,
            'debit': debit,
            'journal_id': asset.profile_id.journal_id.id,
            'partner_id': asset.partner_id.id,
            'analytic_account_id': analytic_id,
            'date': depreciation_date,
            'asset_id': asset.id,
            'analytic_tag_ids': asset.analytic_tag_ids.ids
        }
        return move_line_data
