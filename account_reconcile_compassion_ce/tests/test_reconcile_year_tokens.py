from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReconcileYearTokens(TransactionCase):
    """T3677 A year in the payer's message must not find an invoice"""

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
        cls.sponsor = cls.env["res.partner"].create({"name": "T3677 Sponsor"})
        cls.receivable_account = cls.sponsor.with_company(
            cls.company
        ).property_account_receivable_id
        # Same options as "Invoice matching rule" of Compassion Suisse
        cls.rule = cls.env["account.reconcile.model"].create(
            {
                "name": "T3677 label and reference",
                "rule_type": "invoice_matching",
                "match_text_location_label": True,
                "match_text_location_reference": True,
                "auto_reconcile": True,
                "past_months_limit": 0,
                "company_id": cls.company.id,
            }
        )
        cls.sponsorship_item = cls._open_item(
            "000000000151105200001900006", "1 Patenschaft. Periode: Oktober 2026."
        )

    @classmethod
    def _open_item(cls, payment_reference, customer_reference, amount=50.0):
        move = cls.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": cls.misc_journal.id,
                "date": fields.Date.today(),
                "ref": customer_reference,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": cls.receivable_account.id,
                            "partner_id": cls.sponsor.id,
                            "name": payment_reference,
                            "debit": amount,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": cls.income_account.id,
                            "partner_id": cls.sponsor.id,
                            "name": "T3677 income",
                            "credit": amount,
                        },
                    ),
                ],
            }
        )
        move.action_post()
        return move.line_ids.filtered(
            lambda line: line.account_id == cls.receivable_account
        )

    def _payment(self, label, reference, amount=150.0):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "date": fields.Date.today(),
                "amount": amount,
                "payment_ref": label,
                "partner_id": self.sponsor.id,
                "ref": reference,
            }
        )

    def test_year_in_message_finds_nothing(self):
        """The QRR/2026/097289 case: a donation whose message names the year"""
        st_line = self._payment(
            "Die Berufsbildung in Burkina Faso unterstützen / Spende 2026",
            "000000000151105200000700632",
        )
        tokens = self.rule._get_invoice_matching_st_line_tokens(st_line)[0]
        self.assertNotIn("2026", tokens)
        self.assertFalse(
            self.rule._get_invoice_matching_amls_candidates(st_line, self.sponsor)
        )
        self.assertFalse(self.rule._apply_rules(st_line, self.sponsor))

    def test_reference_still_matches(self):
        st_line = self._payment(
            "Spende 2026", "000000000151105200001900006", amount=50.0
        )
        candidates = self.rule._get_invoice_matching_amls_candidates(
            st_line, self.sponsor
        )
        self.assertEqual(candidates["amls"], self.sponsorship_item)
        self.assertTrue(candidates["allow_auto_reconcile"])

    def test_customer_reference_still_matches(self):
        """An item known only by its customer reference (e.g. a collection)"""
        item = self._open_item("Kollekte", "A200021556409542", amount=85.87)
        st_line = self._payment(
            "Kollektenuebergabe GD 02.08.2026 (A200021556409542)", "", amount=85.87
        )
        candidates = self.rule._get_invoice_matching_amls_candidates(
            st_line, self.sponsor
        )
        self.assertEqual(candidates["amls"], item)

    def test_longer_numbers_are_kept(self):
        st_line = self._payment("Invoice 20261 and 1999123", "")
        tokens = self.rule._get_invoice_matching_st_line_tokens(st_line)[0]
        self.assertIn("20261", tokens)
        self.assertIn("1999123", tokens)
