# Copyright 2026 Compassion CH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import time

from odoo.tests import Form, tagged

from odoo.addons.account_reconcile_oca.tests.test_bank_account_reconcile import (
    TestAccountReconciliationCommon,
)


@tagged("post_install", "-at_install")
class TestReconcileUtm(TestAccountReconciliationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.campaign = cls.env["utm.campaign"].create({"title": "Test campaign"})
        cls.medium = cls.env["utm.medium"].create({"name": "Test medium"})
        cls.source = cls.env["utm.source"].create({"name": "Test source"})
        cls.income_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "income"),
                ("company_ids", "in", cls.env.company.id),
            ],
            limit=1,
        )

    def _create_statement_line(self):
        return self.acc_bank_stmt_line_model.create(
            {
                "name": "testLine",
                "journal_id": self.bank_journal_euro.id,
                "amount": 100,
                "date": time.strftime("%Y-07-15"),
            }
        )

    def _reconcile_with_income(self, st_line):
        with Form(
            st_line,
            view="account_reconcile_oca.bank_statement_line_form_reconcile_view",
        ) as f:
            f.manual_reference = "reconcile_auxiliary;1"
            f.manual_account_id = self.income_account
            f.campaign_id = self.campaign
            f.medium_id = self.medium
            f.source_id = self.source
        st_line.reconcile_bank_line()

    def test_edit_mode(self):
        st_line = self._create_statement_line()
        self._reconcile_with_income(st_line)
        self.assertTrue(st_line.is_reconciled)
        move = st_line.move_id
        self.assertEqual(move.campaign_id, self.campaign)
        self.assertEqual(move.medium_id, self.medium)
        self.assertEqual(move.source_id, self.source)
        self.assertIn(self.income_account, move.line_ids.account_id)

    def test_keep_mode(self):
        self.bank_journal_euro.reconcile_mode = "keep"
        self.bank_journal_euro.suspense_account_id.reconcile = True
        st_line = self._create_statement_line()
        self._reconcile_with_income(st_line)
        self.assertTrue(st_line.is_reconciled)
        counterpart_move = (
            st_line.line_ids._all_reconciled_lines()
            .filtered(lambda line: line.move_id != st_line.move_id)
            .move_id
        )
        self.assertTrue(counterpart_move)
        self.assertEqual(counterpart_move.campaign_id, self.campaign)
        self.assertEqual(counterpart_move.medium_id, self.medium)
        self.assertEqual(counterpart_move.source_id, self.source)
