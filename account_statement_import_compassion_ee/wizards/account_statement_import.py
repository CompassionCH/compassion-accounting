import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountStatementImport(models.TransientModel):
    _inherit = "account.statement.import"

    def _import_file(self):
        res = super()._import_file()
        statements = self.env["account.bank.statement"].browse(res["statement_ids"])
        line_to_reconcile = statements.mapped("line_ids")
        if line_to_reconcile:
            _logger.info(
                "Launching reconciliation of %d statement lines", len(line_to_reconcile)
            )
            line_to_reconcile.with_delay_sh(
                "_cron_try_auto_reconcile_statement_lines",
                channel="root.accounting",
                priority=100,
                description="Auto Reconcile statement lines",
            )
        else:
            _logger.warning("No statement lines to reconcile")
        return res
