# -*- coding: utf-8 -*-
from odoo import api, models

import base64


class AccountStatementImportCustomCamt053(models.TransientModel):
    _inherit = 'account.bank.statement.import'

    @api.model
    def _complete_stmts_vals(self, stmts_vals, journal, account_number):
        # When a return transaction is found, it search for the
        # opposite transaction (same ref).

        stmts_vals = super(AccountStatementImportCustomCamt053, self).\
            _complete_stmts_vals(stmts_vals, journal, account_number)

        list_transactions = stmts_vals[0]['transactions']

        for transaction in list_transactions:
            if transaction.get('sub_fmly_cd') == 'RRTN'\
                    and 'account_id' in transaction \
                    and 'ref' in transaction:

                for transactionBis in list_transactions:
                    if 'ref' in transactionBis \
                            and transactionBis['ref'] == transaction['ref']\
                            and transactionBis != transaction:

                        transactionBis['account_id'] =\
                            transaction['account_id']

        return stmts_vals

    def _create_bank_statements(self, stmts_vals):
        statement_ids, notifications =\
            super(AccountStatementImportCustomCamt053, self).\
            _create_bank_statements(stmts_vals)

        if 'data_file' in stmts_vals[0]:
            # Add the file imported file to the statement.
            if 'file_name' in stmts_vals[0]:
                file_name = stmts_vals[0]['file_name']
            else:
                file_name = self.filename

            self.env['ir.attachment'].create({
                'datas_fname': file_name,
                'res_model': 'account.bank.statement',
                'datas': base64.b64encode(stmts_vals[0]['data_file']),
                'name': file_name,
                'res_id': statement_ids[0]})

        return statement_ids, notifications
