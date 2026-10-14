from odoo.tests import TransactionCase


class TestResConfigSettings(TransactionCase):
    def test_settings_of_a_new_company(self):
        """The settings open for a company without recurring_contract params."""
        company = self.env["res.company"].create({"name": "New company"})
        settings = self.env["res.config.settings"].with_company(company)
        self.assertFalse(
            settings.default_get(["invoice_cleanup_user_id"]).get(
                "invoice_cleanup_user_id"
            )
        )
        # What the settings form does when it opens.
        result = settings.onchange(
            {}, [], {"invoice_cleanup_user_id": {"fields": {"display_name": {}}}}
        )
        self.assertFalse(result["value"]["invoice_cleanup_user_id"])

    def test_cleanup_user_saved_per_company(self):
        settings = self.env["res.config.settings"].create(
            {"invoice_cleanup_user_id": self.env.user.id}
        )
        settings.execute()
        self.assertEqual(
            self.env["res.config.settings"].default_get(["invoice_cleanup_user_id"])[
                "invoice_cleanup_user_id"
            ],
            self.env.user.id,
        )
