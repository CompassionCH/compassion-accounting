# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-today Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: David Wulliamoz <dwulliamoz@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

import logging
from functools import reduce

from odoo import _, models
class BankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def _create_counterpart_and_new_aml(self, counterpart_moves, counterpart_aml_dicts, new_aml_dicts):
        """
        With these two lines, all the donations accounting can be off-balance.

        the real income is to be booked (once a month) in a batch move, from the outstanding account to the different income account
        """
        res = super()._create_counterpart_and_new_aml(counterpart_moves, counterpart_aml_dicts, new_aml_dicts)

        company = res.company_id
        param_obj = self.env["res.config.settings"].sudo().with_company(company)
        account_offbalance_receivable = (param_obj.get_param("account_offbalance_receivable"))
        account_offbalance_asset = (param_obj.get_param("account_offbalance_asset"))
        if account_offbalance_receivable in res.line_ids.mapped("account_id.id"):
            self.move_id.line_ids += (
                self.env["account.move.line"].with_context(check_move_validity=False).create(
                    {"account_id": account_offbalance_asset, "move_id": res.id, "debit": self.amount,
                     "credit": 0}
                ) + self.env["account.move.line"].with_context(check_move_validity=False).create(
                {"account_id": res.journal_id.payment_debit_account_id.id, "move_id": res.id, "debit": 0,
                 "credit": self.amount}))
        return res
