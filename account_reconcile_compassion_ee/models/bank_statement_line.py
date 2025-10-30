from odoo import _, fields, models
from odoo.exceptions import UserError


class BankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def auto_reconcile_statement_lines(self):
        """Extracted from the auto_reconcile_statement_lines cron job to be called
        independently and on selected lines."""
        # The field `cron_last_check` will be written on all processed lines
        # which requires them to be protected against
        # concurrent update in order to avoid the whole transaction to be rollbacked.
        self.env.cr.execute(
            "SELECT 1 FROM account_bank_statement_line WHERE id in %s FOR UPDATE",
            [tuple(self.ids)],
        )

        nb_auto_reconciled_lines = 0
        start_time = fields.Datetime.now()
        for st_line in self:
            wizard = (
                self.env["bank.rec.widget"]
                .with_context(default_st_line_id=st_line.id)
                .new({})
            )
            wizard._action_trigger_matching_rules()
            if wizard.state == "valid" and wizard.matching_rules_allow_auto_reconcile:
                try:
                    wizard._action_validate()
                    if st_line.is_reconciled:
                        st_line.move_id.message_post(
                            body=_(
                                "This bank transaction has been automatically "
                                "validated using the reconciliation model '%s'.",
                                ", ".join(
                                    st_line.move_id.line_ids.reconcile_model_id.mapped(
                                        "name"
                                    )
                                ),
                            )
                        )
                        nb_auto_reconciled_lines += 1
                except UserError:
                    continue

        self.write({"cron_last_check": start_time})
