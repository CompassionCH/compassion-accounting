# -*- coding: utf-8 -*-
from odoo import models


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    # Todo shoud autoreconcile at the close of a statement
    # def button_confirm_bank(self):
    #
    #     account_bank_stmt_line_obj = self.env['account.bank.statement.line']
    #
    #     super(AccountBankStatement, self).button_confirm_bank()
    #
    #     account_bank_stmt_line_obj.camt054_reconcile(self.journal_id.default_debit_account_id.code)
