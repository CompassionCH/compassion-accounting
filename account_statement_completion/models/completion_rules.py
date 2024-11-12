##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

import logging
import re

from odoo import fields, models
from odoo.tools import safe_eval
from odoo.tools.safe_eval import wrap_module

logger = logging.getLogger(__name__)


class Journal(models.Model):
    """Add completion rules to journals"""

    _inherit = "account.journal"

    completion_rules = fields.Many2many(
        "account.statement.completion.rule", readonly=False
    )


class StatementCompletionRule(models.Model):
    """Rules to complete account bank statements."""

    _name = "account.statement.completion.rule"
    _description = "Account Statement Completion Rule"

    DEFAULT_VAL = """
# Available variables:
#-------------------------------
# stmts_vals: Values of the statements as a list of dict
# stmt_line: Values of the statement line as a dict
# env: environment
# re.search, re.findall: regex functions for finding values in strings

# Available compute variables:
#-------------------------------
# result: True if the reconcilation rule found any relevant data.
#         This will prevent any subsequent rule to be executed on the same line.

# Example:
#-------------------------------
# result = True
                    """

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################

    sequence = fields.Integer("Sequence", help="Lower means parsed first.")
    name = fields.Char("Name", size=128)
    journal_ids = fields.Many2many(
        "account.journal", string="Related statement journal", readonly=False
    )

    python_completion_rule = fields.Text(
        string="Python Code", default=DEFAULT_VAL, help=DEFAULT_VAL
    )

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################

    def auto_complete(self, stmt_vals):
        """This method will execute all related rules, in their sequence order,
        to retrieve all the values returned by the first rules that will match.
        :param stmt_vals: dict with bank statement values
        return:
            A dict of values for the bank statement line or {}
           {'partner_id': value,
            'account_id': value,
            ...}
        """
        stmt_lines_vals = stmt_vals.get("transactions", list())
        for stmt_line_vals in stmt_lines_vals:
            for rule in self.sorted(key=lambda r: r.sequence):
                eval_dict = rule._get_base_dict(stmt_vals, stmt_line_vals)
                safe_eval.safe_eval(
                    rule.python_completion_rule, eval_dict, mode="exec", nocopy=True
                )
                if eval_dict.get("result"):
                    break
        return dict()

    def _get_base_dict(self, stmts_vals, stmt_line):
        """Return the values usable in the code template"""
        return {
            "result": False,
            "stmts_vals": stmts_vals,
            "stmt_line": stmt_line,
            "env": self.env,
            "re": wrap_module(re, ["search", "findall"]),
            "logger": logger,
        }
