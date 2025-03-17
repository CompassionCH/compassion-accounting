from odoo import models


class AccountStatementImport(models.TransientModel):
    _inherit = "account.statement.import"

    def _import_file(self):
        res = super()._import_file()
        statements = self.env["account.bank.statement"].browse(res["statement_ids"])
        line_to_reconcile = statements.mapped("line_ids")
        if line_to_reconcile:
            line_to_reconcile.with_delay(
                channel="root.accounting",
                priority=100,
                description="Auto Reconcile statement lines",
            )._cron_try_auto_reconcile_statement_lines()
        return res
