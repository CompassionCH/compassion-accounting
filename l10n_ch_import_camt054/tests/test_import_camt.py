# -*- coding: utf-8 -*-
import base64

from odoo.tests import SingleTransactionCase
from odoo.modules import get_module_resource


class TestImportCamt(SingleTransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestImportCamt, cls).setUpClass()

        account_bank_statement_import_obj = \
            cls.env['account.bank.statement.import']

        account_bank_statement_line_obj = \
            cls.env['account.bank.statement.line']

        account_account_obj = cls.env['account.account']
        account_move_line_obj = cls.env['account.move.line']

        test_file_path_camt053 = get_module_resource(
            'l10n_ch_import_camt054', 'res', 'camt.053.demo-1000.xml')
        test_file_path_camt054 = get_module_resource(
            'l10n_ch_import_camt054', 'res', 'camt.054.demo-1000.xml')

        # Open the file
        file_to_import_053 = open(test_file_path_camt053, 'r')
        file_to_import_054 = open(test_file_path_camt054, 'r')
        # Get the content of the file and remove the line return
        data053 = file_to_import_053.read()
        data054 = file_to_import_054.read()
        data053 = data053.replace("\n", "")
        data054 = data054.replace("\n", "")
        # Convert the content in base 64
        data053_64 = base64.b64encode(data053)
        data054_64 = base64.b64encode(data054)

        # import the file in the journal
        bank_import_053 = account_bank_statement_import_obj.create({
            'data_file': data053_64,
            'filename': 'camt.053.demo-1000.xml'
        })
        bank_import_054 = account_bank_statement_import_obj.create({
            'data_file': data054_64,
            'filename': 'camt.054.demo-1000.xml'
        })

        bank_import_053.import_file()
        bank_import_054.import_file()

        account_1098 = account_account_obj.search([('code', '=', '1098')])
        account_1050 = account_account_obj.search([('code', '=', '1050')])

        statement_line_camt053 = account_bank_statement_line_obj.search([
            ('name', '=', 'Demo Camt053')])

        # Reconcile line from the camt 053
        new_aml_dicts = []
        new_aml_dicts.append({"account_id": account_1098.id,
                              "credit": 1000,
                              "debit": 0,
                              "name": statement_line_camt053.name})

        statement_line_camt053.process_reconciliation([],
                                                      account_move_line_obj,
                                                      new_aml_dicts)

        # Reconcile line from the camt 054
        statement_line_camt054 = account_bank_statement_line_obj.search(
            [('name', '=', 'Demo Camt054')])

        for statement_line in statement_line_camt054:
            new_aml_dicts = []
            new_aml_dicts.append({"account_id": account_1050.id,
                                  "credit": statement_line.amount,
                                  "debit": 0,
                                  "name": statement_line.name})
            statement_line.process_reconciliation([],
                                                  account_move_line_obj,
                                                  new_aml_dicts)

    # Tests for camt053
    def test_camt053_imported(self):
        statement = self.env['account.bank.statement'].search([
            ('reference', '=', 'camt.053.demo-1000.xml')])

        self.assertTrue(statement)

    def test_statement053_is_open(self):
        statement = self.env['account.bank.statement'].search(
            [('state', '=', 'open')])

        self.assertTrue(statement)

    def test_move_line053_exist(self):
        move_lines = self.env['account.move.line'].search(
            [('name', '=', 'Demo Camt053')])

        self.assertTrue(move_lines)

    # Tests for camt054
    def test_camt054_imported(self):
        statement = self.env['account.bank.statement'].search([
            ('reference', '=', 'camt.054.demo-1000.xml')])

        self.assertTrue(statement)

    def test_statement054_is_open(self):
        statement = self.env['account.bank.statement'].search(
            [('state', '=', 'open')])

        self.assertTrue(statement)

    def test_move_line054_exist(self):
        move_lines = self.env['account.move.line'].search(
            [('name', '=', 'Demo Camt054')])

        self.assertTrue(move_lines)
    # Test final reconciliation

    def test_move_line_are_reconcilied(self):
        account_bank_statement_line_obj =\
            self.env['account.bank.statement.line']

        account_1098 = self.env['account.account'].search(
            [('code', '=', '1098')])

        account_bank_statement_line_obj.camt054_reconcile('1098')

        move_lines = self.env['account.move.line'].search(
            [('acct_svcr_ref', '=', '99999999999999999999999999999999'),
             ('account_id', '=', account_1098.id)])

        for move_line in move_lines:
            self.assertTrue(move_line.reconciled)
