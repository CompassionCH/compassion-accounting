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

from odoo import api, models, fields
from odoo.tools import safe_eval

logger = logging.getLogger(__name__)


class Journal(models.Model):
    """ Add completion rules to journals """
    _inherit = 'account.journal'

    completion_rules = fields.Many2many('account.statement.completion.rule',
                                        readonly=False)


class StatementCompletionRule(models.Model):
    """ Rules to complete account bank statements."""
    _name = "account.statement.completion.rule"
    _description = 'Account Statement Completion Rule'

    DEFAULT_VAL = """
                    # Available variables:
                    #-------------------------------
                    # stmts_vals: Values of the statements as a list of dict
                    # stmt_line: Values of the statement line as a dict
                    # line_amount: stmt_line amount
                    # ref: stmt_line reference
                    # AccMove: Odoo model "account.move"
                    # AccMoveLine: Odoo model "account.move.line"
                    # Partner: Odoo model "res.partner".
                    # Payment: Odoo model "account.payment"
                    # PaymentLine: Odoo model "account.payment.line"

                    # Available compute variables:
                    #-------------------------------
                    # result: returned value have to be set in the variable 'result'

                    # Example:
                    #-------------------------------
                    # result = stmt_vals[0].partner_id

                    """

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################

    sequence = fields.Integer('Sequence',
                              help="Lower means parsed first.")
    name = fields.Char('Name', size=128)
    journal_ids = fields.Many2many(
        'account.journal',
        string='Related statement journal', readonly=False)

    python_completion_rule = fields.Text(
        string="Python Code",
        default=DEFAULT_VAL,
        help=DEFAULT_VAL
    )

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################

    def auto_complete(self, stmts_vals, stmt_line):
        """This method will execute all related rules, in their sequence order,
        to retrieve all the values returned by the first rules that will match.
        :param stmts_vals: dict with bank statement values
        :param dict stmt_line: dict with statement line values
        :return:
            A dict of values for the bank statement line or {}
           {'partner_id': value,
            'account_id': value,
            ...}
        """
        for rule in self.sorted(key=lambda r: r.sequence):
            eval_dict = rule._get_base_dict(stmts_vals, stmt_line)
            safe_eval.safe_eval(
                rule.python_completion_rule,
                eval_dict,
                mode="exec",
                nocopy=True
            )
            result = eval_dict.get("result", {})
            if result:
                return result
        return dict()

    def _get_base_dict(self, stmts_vals, stmt_line):
        """ Return the values usable in the code template """
        return {
            "result": {},
            "stmts_vals": stmts_vals,
            "stmt_line": stmt_line,
            "line_amount": stmt_line["amount"],
            "ref": stmt_line.get('ref', False),
            "AccMove": self.env["account.move"],
            "AccMoveLine": self.env["account.move.line"],
            "Partner": self.env["res.partner"],
            "Payment": self.env["account.payment"],
            "PaymentLine": self.env["account.payment.line"]
        }
