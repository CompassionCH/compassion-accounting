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
                "company_ids": [(4, cls.company.id)],
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
                "company_ids": [(4, cls.company.id)],
            }
        )

        # Create off-balance asset account
        cls.off_balance_asset_account = cls.Account.create(
            {
                "name": "Off-Balance Asset",
                "code": "OBX200",
                "account_type": "asset_current",
                "is_off_balance": True,
                "company_ids": [(4, cls.company.id)],
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
                "company_ids": [(4, cls.company.id)],
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
                "company_ids": [(4, cls.company.id)],
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
