import logging
import time

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def auto_reconcile_statement_lines(self):
        """Extracted from the auto_reconcile_statement_lines cron job to be called
        independently and on selected lines."""
        # The field `cron_last_check` will be written on all processed lines
        # which requires them to be protected against
        # concurrent update in order to avoid the whole transaction to be rollbacked.
        _logger.info(
            "auto_reconcile_statement_lines: acquiring row-level lock for %d lines: %s",
            len(self),
            self.ids,
        )
        self.env.cr.execute(
            "SELECT 1 FROM account_bank_statement_line WHERE id in %s FOR UPDATE",
            [tuple(self.ids)],
        )

        nb_auto_reconciled_lines = 0
        start_time = fields.Datetime.now()
        start_perf = time.perf_counter()
        _logger.info("auto_reconcile_statement_lines: started at %s", start_time)

        for st_line in self:
            _logger.info(
                "Processing bank statement line id=%s, name=%s",
                st_line.id,
                getattr(st_line, "name", "<no-name>"),
            )
            wizard = (
                self.env["bank.rec.widget"]
                .with_context(default_st_line_id=st_line.id)
                .new({})
            )
            wizard._action_trigger_matching_rules()
            _logger.info(
                "After triggering matching rules: wizard.state=%s, "
                "matching_rules_allow_auto_reconcile=%s",
                getattr(wizard, "state", None),
                getattr(wizard, "matching_rules_allow_auto_reconcile", None),
            )
            if wizard.state == "valid" and wizard.matching_rules_allow_auto_reconcile:
                _logger.info(
                    "Attempting auto-validate for statement line %s", st_line.id
                )
                try:
                    wizard._action_validate()
                    if st_line.is_reconciled:
                        model_names = ", ".join(
                            st_line.move_id.line_ids.reconcile_model_id.mapped("name")
                        )
                        _logger.info(
                            "Line %s auto-reconciled using model(s): %s",
                            st_line.id,
                            model_names,
                        )
                        st_line.move_id.message_post(
                            body=_(
                                "This bank transaction has been automatically "
                                "validated using the reconciliation model '%s'.",
                                model_names,
                            )
                        )
                        nb_auto_reconciled_lines += 1
                    else:
                        _logger.warning(
                            "Validation ran but line %s is not reconciled", st_line.id
                        )
                except UserError as err:
                    # Log why the validation failed for this line and continue
                    _logger.warning(
                        "UserError while auto-validating line %s: %s", st_line.id, err
                    )
                    continue

        elapsed = time.perf_counter() - start_perf
        _logger.info(
            "auto_reconcile_statement_lines: finished. "
            "auto-reconciled %d/%d lines in %.3fs",
            nb_auto_reconciled_lines,
            len(self),
            elapsed,
        )

        # write the last check timestamp
        self.write({"cron_last_check": start_time})
