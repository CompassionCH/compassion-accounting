##############################################################################
#
#    Copyright (C) 2014-today Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: David Wulliamoz <dwulliamoz@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import fields, models


class OffBalanceAccountConfigSettings(models.TransientModel):
    """
    Add the possibility to define an off balance asset account
    and off balance receivable account
    """

    _inherit = "res.config.settings"

    off_balance_asset_account_id = fields.Many2one(
        "account.account",
        related="company_id.off_balance_asset_account_id",
        readonly=False,
    )
