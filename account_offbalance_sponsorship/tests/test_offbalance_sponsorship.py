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


class TestOffBalanceAccount(TransactionCase):
    """Tests for the account.account off-balance extensions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["account.account"]
        cls.Company = cls.env["res.company"]
        cls.company = cls.env.company

        # Create on-balance account
        cls.on_balance_account = cls.Account.create(
            {
                "name": "On-Balance Income",
                "code": "OB100",
                "account_type": "income",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )

        # Create off-balance account
        cls.off_balance_account = cls.Account.create(
            {
                "name": "Off-Balance Income",
                "code": "OBX100",
                "account_type": "income",
                "is_off_balance": True,
                "on_balance_account_id": cls.on_balance_account.id,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )

        # Create off-balance asset account
        cls.off_balance_asset_account = cls.Account.create(
            {
                "name": "Off-Balance Asset",
                "code": "OBX200",
                "account_type": "asset_current",
                "is_off_balance": True,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )

    def test_account_is_off_balance_field(self):
        """Test that is_off_balance field is correctly set."""
        self.assertTrue(self.off_balance_account.is_off_balance)
        self.assertFalse(self.on_balance_account.is_off_balance)

    def test_account_on_balance_account_id_link(self):
        """Test that on_balance_account_id is correctly linked."""
        self.assertEqual(
            self.off_balance_account.on_balance_account_id, self.on_balance_account
        )
        self.assertFalse(self.on_balance_account.on_balance_account_id)

    def test_onchange_is_off_balance_clears_link(self):
        """Test that unchecking is_off_balance clears the on_balance_account_id."""
        # Simulate the onchange by calling it directly
        self.off_balance_account.is_off_balance = False
        self.off_balance_account.onchange_is_off_balance()
        self.assertFalse(self.off_balance_account.on_balance_account_id)

    def test_account_search_filter_off_balance_context(self):
        """Test that _search filters off-balance accounts when context is set."""
        # Search without filter
        all_accounts = self.Account.search([("code", "like", "OB%")])
        self.assertIn(self.off_balance_account, all_accounts)
        self.assertIn(self.on_balance_account, all_accounts)

        # Search with filter_off_balance context
        filtered_accounts = self.Account.with_context(filter_off_balance=True).search(
            [("code", "like", "OB%")]
        )
        self.assertNotIn(self.off_balance_account, filtered_accounts)
        self.assertIn(self.on_balance_account, filtered_accounts)


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
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.off_balance_account = cls.Account.create(
            {
                "name": "Off-Balance Income",
                "code": "OBMX100",
                "account_type": "income",
                "is_off_balance": True,
                "on_balance_account_id": cls.on_balance_account.id,
                "company_ids": [(6, 0, [cls.company.id])],
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


class TestOffBalanceResCompany(TransactionCase):
    """Tests for the res.company off-balance extensions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["account.account"]
        cls.company = cls.env.company

        # Create off-balance asset account
        cls.off_balance_asset_account = cls.Account.create(
            {
                "name": "Off-Balance Asset Company Test",
                "code": "OBC200",
                "account_type": "asset_current",
                "is_off_balance": True,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )

    def test_company_off_balance_asset_account_id_field(self):
        """Test that off_balance_asset_account_id field can be set on company."""
        self.company.off_balance_asset_account_id = self.off_balance_asset_account
        self.assertEqual(
            self.company.off_balance_asset_account_id, self.off_balance_asset_account
        )

    def test_company_off_balance_asset_account_id_unset(self):
        """Test that off_balance_asset_account_id can be unset."""
        self.company.off_balance_asset_account_id = False
        self.assertFalse(self.company.off_balance_asset_account_id)


class TestOffBalanceResConfigSettings(TransactionCase):
    """Tests for the res.config.settings off-balance extensions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["account.account"]
        cls.ConfigSettings = cls.env["res.config.settings"]
        cls.company = cls.env.company

        # Create off-balance asset account
        cls.off_balance_asset_account = cls.Account.create(
            {
                "name": "Off-Balance Asset Config Test",
                "code": "OBCFG200",
                "account_type": "asset_current",
                "is_off_balance": True,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )

    def test_config_settings_off_balance_asset_account_id_related(self):
        """Test that config settings has related field to company."""
        # Set the account on company
        self.company.off_balance_asset_account_id = self.off_balance_asset_account

        # Create config settings and check the related field
        config = self.ConfigSettings.create({})
        self.assertEqual(
            config.off_balance_asset_account_id, self.off_balance_asset_account
        )

    def test_config_settings_can_update_company_field(self):
        """Test that updating config settings updates company field."""
        # Create config settings
        config = self.ConfigSettings.create(
            {"off_balance_asset_account_id": self.off_balance_asset_account.id}
        )
        config.set_values()

        # Check company field was updated
        self.assertEqual(
            self.company.off_balance_asset_account_id, self.off_balance_asset_account
        )
