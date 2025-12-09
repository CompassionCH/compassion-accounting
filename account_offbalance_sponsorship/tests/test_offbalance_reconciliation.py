##############################################################################
#
#       ______ Releasing children from poverty      _
#      / ____/___  ____ ___  ____  ____ ___________(_)___  ____
#     / /   / __ \/ __ `__ \/ __ \/ __ `/ ___/ ___/ / __ \/ __ \
#    / /___/ /_/ / / / / / / /_/ / /_/ (__  |__  ) / /_/ / / / /
#    \____/\____/_/ /_/ /_/ .___/\__,_/____/____/_/\____/_/ /_/
#                        /_/
#                            in Jesus' name
#
#    Copyright (C) 2014-today Compassion CH (http://www.compassion.ch)
#    @author: David Wulliamoz <dwulliamoz@compassion.ch>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from odoo.tests.common import TransactionCase


class TestOffBalanceAccountMoveLine(TransactionCase):
    """Tests for the account.move.line off-balance extensions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["account.account"]
        cls.AccountMove = cls.env["account.move"]
        cls.AccountMoveLine = cls.env["account.move.line"]
        cls.company = cls.env.company

        # Create accounts
        cls.on_balance_account = cls.Account.create(
            {
                "name": "On-Balance Income",
                "code": "OBM100",
                "account_type": "income",
                "company_ids": [(4, cls.company.id)],
            }
        )
        cls.off_balance_account = cls.Account.create(
            {
                "name": "Off-Balance Income",
                "code": "OBMX100",
                "account_type": "income",
                "is_off_balance": True,
                "on_balance_account_id": cls.on_balance_account.id,
                "company_ids": [(4, cls.company.id)],
            }
        )

        # Create a journal
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Test Journal",
                "code": "TJ",
                "type": "general",
                "company_id": cls.company.id,
            }
        )

        # Create a simple journal entry with both off-balance and regular lines
        cls.move = cls.AccountMove.create(
            {
                "journal_id": cls.journal.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Off-balance line",
                            "account_id": cls.off_balance_account.id,
                            "debit": 100.0,
                            "credit": 0.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "On-balance line",
                            "account_id": cls.on_balance_account.id,
                            "debit": 0.0,
                            "credit": 100.0,
                        },
                    ),
                ],
            }
        )

    def test_is_off_balance_generated_field(self):
        """Test that is_off_balance_generated field exists and defaults to False."""
        for line in self.move.line_ids:
            self.assertFalse(line.is_off_balance_generated)

    def test_move_line_search_filter_off_balance_context(self):
        """Test that _search filters off-balance move lines when context is set."""
        # Get line ids from our test move
        move_line_ids = self.move.line_ids.ids

        # Search without filter
        all_lines = self.AccountMoveLine.search([("id", "in", move_line_ids)])
        self.assertEqual(len(all_lines), 2)

        # Search with filter_off_balance context
        filtered_lines = self.AccountMoveLine.with_context(
            filter_off_balance=True
        ).search([("id", "in", move_line_ids)])
        self.assertEqual(len(filtered_lines), 1)
        self.assertEqual(filtered_lines.account_id, self.on_balance_account)
