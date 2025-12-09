from odoo import fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("-at_install", "post_install")
class TestOffBalanceExchangeDifference(AccountTestInvoicingCommon):
    """
    Tests for off-balance exchange difference handling.

    This test suite verifies that the _prepare_exchange_difference_move_vals
    method properly replaces the exchange rate account with the off-balance
    equivalent when dealing with off-balance lines.
    """

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.Account = cls.env["account.account"]
        cls.AccountMove = cls.env["account.move"]
        cls.AccountMoveLine = cls.env["account.move.line"]
        cls.Currency = cls.env["res.currency"]
        cls.company = cls.env.company

        # Get or create a foreign currency
        cls.foreign_currency = cls.env.ref("base.USD")
        if cls.foreign_currency == cls.company.currency_id:
            # If USD is company currency, use EUR instead
            cls.foreign_currency = cls.env.ref("base.EUR")

        # Setup exchange rate account (standard Odoo account for exchange differences)
        cls.exchange_diff_account = cls.company_data.get(
            "default_account_expense"
        ) or cls.Account.search(
            [
                ("account_type", "=", "expense"),
                ("company_id", "=", cls.company.id),
            ],
            limit=1,
        )

        # Create off-balance version of exchange difference account
        cls.off_balance_exchange_account = cls.Account.create(
            {
                "name": "Off-Balance Exchange Difference",
                "code": "EXDXEX100",
                "account_type": "expense",
                "is_off_balance": True,
                "on_balance_account_id": cls.exchange_diff_account.id,
                "company_id": cls.company.id,
            }
        )

        # Setup off-balance income account
        cls.on_balance_income_account = cls.company_data["default_account_revenue"]
        cls.off_balance_income_account = cls.Account.create(
            {
                "name": "Off-Balance Income",
                "code": "INCXEX200",
                "account_type": "income",
                "is_off_balance": True,
                "on_balance_account_id": cls.on_balance_income_account.id,
                "company_id": cls.company.id,
            }
        )

        # Create off-balance asset account
        cls.off_balance_asset_account = cls.Account.create(
            {
                "name": "Off-Balance Asset",
                "code": "ASSXEX200",
                "account_type": "asset_current",
                "is_off_balance": True,
                "company_id": cls.company.id,
            }
        )

        # Setup receivable accounts
        cls.receivable_account = cls.company_data["default_account_receivable"]
        cls.receivable_offbalance = cls.copy_account(
            cls.receivable_account,
            {
                "is_off_balance": True,
                "on_balance_account_id": cls.receivable_account.id,
            },
        )

        # Set the off-balance asset account on company
        cls.company.off_balance_asset_account_id = cls.off_balance_asset_account

        # Update partner's account
        cls.partner_a.property_account_receivable_id = cls.receivable_offbalance

        # Create product with off-balance income account
        cls.product_off_balance = cls.env["product.product"].create(
            {
                "name": "Off-Balance Product",
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
                "uom_po_id": cls.env.ref("uom.product_uom_unit").id,
                "lst_price": 1000.0,
                "property_account_income_id": cls.off_balance_income_account.id,
                "property_account_expense_id": cls.company_data[
                    "default_account_expense"
                ].id,
                "taxes_id": False,
            }
        )

        # Create journal
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Test Journal Exchange",
                "code": "TJEX",
                "type": "general",
                "company_id": cls.company.id,
            }
        )

    def test_exchange_difference_uses_offbalance_account(self):
        """
        Test that _prepare_exchange_difference_move_vals replaces
        the exchange rate account with off-balance account.

        Steps:
        1. Create move lines with off-balance income account
        2. Call _prepare_exchange_difference_move_vals
        3. Verify that the exchange account is replaced with off-balance version
        """
        # Step 1: Create move lines with off-balance account and foreign currency
        move = self.AccountMove.create(
            {
                "move_type": "entry",
                "journal_id": self.journal.id,
                "date": fields.Date.today(),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Off-balance income line",
                            "account_id": self.off_balance_income_account.id,
                            "debit": 0.0,
                            "credit": 100.0,
                            "currency_id": self.foreign_currency.id,
                            "amount_currency": -120.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Receivable line",
                            "account_id": self.receivable_offbalance.id,
                            "debit": 100.0,
                            "credit": 0.0,
                            "currency_id": self.foreign_currency.id,
                            "amount_currency": 120.0,
                        },
                    ),
                ],
            }
        )
        move.action_post()

        # Step 2: Prepare exchange difference amounts
        # Simulate an exchange rate difference scenario
        off_balance_line = move.line_ids.filtered(
            lambda mvl: mvl.account_id == self.off_balance_income_account
        )

        # Create amounts list simulating exchange difference
        amounts_list = [
            {
                "aml": off_balance_line,
                "amount_residual": 10.0,
                "amount_residual_currency": 0.0,
                "balance": 100.0,
                "amount_currency": -120.0,
            }
        ]

        # Step 3: Call the method
        result = off_balance_line._prepare_exchange_difference_move_vals(
            amounts_list,
            company=self.company,
            exchange_date=fields.Date.today(),
        )

        # Step 4: Verify the result
        self.assertIn("move_values", result)
        self.assertIn("line_ids", result["move_values"])

        # Find the exchange difference line (should be at position 1 in the list)
        # Structure is: [(0, 0, original_line_vals), (0, 0, exchange_line_vals)]
        line_ids = result["move_values"]["line_ids"]
        self.assertGreaterEqual(
            len(line_ids), 2, "Expected at least 2 lines in the result"
        )

        # The exchange line is the second line (index 1)
        # Each line is a tuple: (0, 0, {field_values_dict})
        exchange_line_vals = line_ids[1][2]

        # Verify that the account is the off-balance exchange account
        self.assertEqual(
            exchange_line_vals["account_id"],
            self.off_balance_exchange_account.id,
            "Exchange difference line should use off-balance exchange account",
        )

        # Verify that the line is marked as generated
        self.assertTrue(
            exchange_line_vals.get("is_off_balance_generated", False),
            "Exchange difference line should be marked as generated",
        )

    def test_exchange_difference_standard_account_unchanged(self):
        """
        Test that _prepare_exchange_difference_move_vals does not modify
        the exchange account for standard (non-off-balance) lines.

        Steps:
        1. Create move lines with standard on-balance income account
        2. Call _prepare_exchange_difference_move_vals
        3. Verify that the exchange account is NOT replaced
        """
        # Step 1: Create move lines with on-balance account
        move = self.AccountMove.create(
            {
                "move_type": "entry",
                "journal_id": self.journal.id,
                "date": fields.Date.today(),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "On-balance income line",
                            "account_id": self.on_balance_income_account.id,
                            "debit": 0.0,
                            "credit": 100.0,
                            "currency_id": self.foreign_currency.id,
                            "amount_currency": -120.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Receivable line",
                            "account_id": self.receivable_account.id,
                            "debit": 100.0,
                            "credit": 0.0,
                            "currency_id": self.foreign_currency.id,
                            "amount_currency": 120.0,
                        },
                    ),
                ],
            }
        )
        move.action_post()

        # Step 2: Prepare exchange difference amounts
        on_balance_line = move.line_ids.filtered(
            lambda mvl: mvl.account_id == self.on_balance_income_account
        )

        amounts_list = [
            {
                "aml": on_balance_line,
                "amount_residual": 10.0,
                "amount_residual_currency": 0.0,
                "balance": 100.0,
                "amount_currency": -120.0,
            }
        ]

        # Step 3: Call the method
        result = on_balance_line._prepare_exchange_difference_move_vals(
            amounts_list,
            company=self.company,
            exchange_date=fields.Date.today(),
        )

        # Step 4: Verify the result - should use standard exchange account
        line_ids = result["move_values"]["line_ids"]
        self.assertGreaterEqual(
            len(line_ids), 2, "Expected at least 2 lines in the result"
        )

        # Each line is a tuple: (0, 0, {field_values_dict})
        exchange_line_vals = line_ids[1][2]

        # For on-balance lines, the account should NOT be the off-balance
        # exchange account
        self.assertNotEqual(
            exchange_line_vals["account_id"],
            self.off_balance_exchange_account.id,
            "Standard lines should not use off-balance exchange account",
        )

        # Verify that the line is NOT marked as generated for standard accounts
        self.assertFalse(
            exchange_line_vals.get("is_off_balance_generated", False),
            "Standard exchange difference line should not be marked as generated",
        )
