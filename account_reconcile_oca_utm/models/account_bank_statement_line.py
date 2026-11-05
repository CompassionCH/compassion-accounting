# Copyright 2026 Compassion CH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models


class AccountBankStatementLine(models.Model):
    """The UTM of a statement line are those of its move (_inherits). In the
    keep mode, the counterparts are booked in another move, which gets them
    too."""

    _inherit = "account.bank.statement.line"

    def _reconcile_bank_line_keep_move_vals(self):
        vals = super()._reconcile_bank_line_keep_move_vals()
        vals.update(
            {
                "campaign_id": self.campaign_id.id,
                "medium_id": self.medium_id.id,
                "source_id": self.source_id.id,
            }
        )
        return vals
