from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReconcileCompanyContacts(TransactionCase):
    """T3677 Automatic matching on the company and all its contacts"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.bank_journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.company.id)], limit=1
        )
        cls.misc_journal = cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1
        )
        cls.income_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "income"),
                ("company_ids", "in", cls.company.id),
            ],
            limit=1,
        )
        partner_model = cls.env["res.partner"]
        cls.organisation = partner_model.create(
            {"name": "T3677 Organisation", "is_company": True}
        )
        cls.contact = partner_model.create(
            {"name": "T3677 Contact", "parent_id": cls.organisation.id}
        )
        cls.other_contact = partner_model.create(
            {"name": "T3677 Other contact", "parent_id": cls.organisation.id}
        )
        cls.person = partner_model.create({"name": "T3677 Person"})
        cls.stranger = partner_model.create({"name": "T3677 Stranger"})
        cls.receivable_account = cls.organisation.with_company(
            cls.company
        ).property_account_receivable_id
        cls.reference_rule = cls.env["account.reconcile.model"].create(
            {
                "name": "T3677 reference",
                "rule_type": "invoice_matching",
                "match_text_location_label": True,
                "auto_reconcile": True,
                "past_months_limit": 0,
                "company_id": cls.company.id,
            }
        )
        cls.proposal_rule = cls.env["account.reconcile.model"].create(
            {
                "name": "T3677 proposal",
                "rule_type": "invoice_matching",
                "match_text_location_label": False,
                "match_text_location_note": False,
                "match_text_location_reference": False,
                "past_months_limit": 0,
                "company_id": cls.company.id,
            }
        )

    def _open_item(self, partner, reference, amount=123.45):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.misc_journal.id,
                "date": fields.Date.today(),
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": self.receivable_account.id,
                            "partner_id": partner.id,
                            "name": f"Open item {reference}",
                            "debit": amount,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": self.income_account.id,
                            "partner_id": partner.id,
                            "name": "T3677 income",
                            "credit": amount,
                        },
                    ),
                ],
            }
        )
        move.action_post()
        return move.line_ids.filtered(
            lambda line: line.account_id == self.receivable_account
        )

    def _payment(self, partner, label, amount=123.45):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "date": fields.Date.today(),
                "amount": amount,
                "payment_ref": label,
                "partner_id": partner.id,
            }
        )

    def test_reference_matches_company_item(self):
        item = self._open_item(self.organisation, "736251904418")
        st_line = self._payment(self.contact, "Payment 736251904418")
        candidates = self.reference_rule._get_invoice_matching_amls_candidates(
            st_line, self.contact
        )
        self.assertTrue(candidates)
        self.assertTrue(candidates["allow_auto_reconcile"])
        self.assertEqual(candidates["amls"], item)
        result = self.reference_rule._apply_rules(st_line, self.contact)
        self.assertEqual(result.get("amls"), item)
        self.assertTrue(result.get("auto_reconcile"))

    def test_reference_matches_other_contact_item(self):
        item = self._open_item(self.other_contact, "736251904419")
        st_line = self._payment(self.contact, "Payment 736251904419")
        candidates = self.reference_rule._get_invoice_matching_amls_candidates(
            st_line, self.contact
        )
        self.assertEqual(candidates["amls"], item)

    def test_company_payment_matches_contact_item(self):
        item = self._open_item(self.contact, "736251904420")
        st_line = self._payment(self.organisation, "Payment 736251904420")
        candidates = self.reference_rule._get_invoice_matching_amls_candidates(
            st_line, self.organisation
        )
        self.assertEqual(candidates["amls"], item)

    def test_proposal_stays_on_exact_partner(self):
        company_item = self._open_item(self.organisation, "736251904421")
        own_item = self._open_item(self.contact, "736251904422")
        st_line = self._payment(self.contact, "Payment without reference")
        candidates = self.proposal_rule._get_invoice_matching_amls_candidates(
            st_line, self.contact
        )
        self.assertFalse(candidates["allow_auto_reconcile"])
        self.assertIn(own_item, candidates["amls"])
        self.assertNotIn(company_item, candidates["amls"])

    def test_person_without_company_unchanged(self):
        self._open_item(self.stranger, "736251904423")
        st_line = self._payment(self.person, "Payment 736251904423")
        candidates = self.reference_rule._get_invoice_matching_amls_candidates(
            st_line, self.person
        )
        self.assertFalse(candidates)
