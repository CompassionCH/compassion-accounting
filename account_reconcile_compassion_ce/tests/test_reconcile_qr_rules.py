from odoo import Command, fields
from odoo.tests import TransactionCase, tagged
from odoo.tools import mod10r


@tagged("post_install", "-at_install")
class TestReconcileQrRules(TransactionCase):
    """T3622 Invoice matching on exactly the QR reference and amount, and the
    QR reference types of a rule."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.bank_journal = cls.env["account.journal"].create(
            {"name": "T3622 QRR", "type": "bank", "code": "T3622"}
        )
        cls.income_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "income"),
                ("company_ids", "in", cls.company.id),
            ],
            limit=1,
        )
        # The partner ref comes from a sequence
        cls.payer = cls.env["res.partner"].create({"name": "T3622 Payer"})
        cls.reference = cls._reference("7", "0105")
        cls.rule = cls.env["account.reconcile.model"].create(
            {
                "name": "T3622 invoice matching",
                "rule_type": "invoice_matching",
                "auto_reconcile": True,
                "match_partner": True,
                "match_text_location_label": True,
                "match_text_location_reference": True,
                "match_exact_reference": True,
                "exact_amount_only": True,
                "past_months_limit": 0,
                "company_id": cls.company.id,
            }
        )

    @classmethod
    def _reference(cls, ref_type, code):
        """9 zeros + partner ref + group 01506 + type + code + check digit"""
        return mod10r(f"{cls.payer.ref:0>16}01506{ref_type}{code}")

    def _invoice(self, amount, reference, partner=None):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": (partner or self.payer).id,
                "invoice_date": fields.Date.today(),
                "payment_reference": reference,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "T3622 sponsorship",
                            "price_unit": amount,
                            "account_id": self.income_account.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        return invoice

    def _payment(self, amount, label=None, ref=False):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "date": fields.Date.today(),
                "amount": amount,
                "payment_ref": label or self.reference,
                "ref": ref,
                "partner_id": self.payer.id,
            }
        )

    def _receivable(self, invoices):
        return invoices.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )

    def test_qr_reference_decoding(self):
        st_line = self._payment(84.0)
        self.assertEqual(st_line._get_qr_reference(), self.reference)
        self.assertEqual(st_line._get_qr_type().code, "7")
        self.assertEqual(st_line._get_qr_partner(), self.payer)
        wrong = self.reference[:-1] + str((int(self.reference[-1]) + 1) % 10)
        self.assertFalse(self._payment(84.0, label=wrong)._get_qr_reference())
        # The bank puts the reference in the move ref when there is a message
        with_message = self._payment(84.0, label="Merci", ref=self.reference)
        self.assertEqual(with_message._get_qr_reference(), self.reference)

    def test_exact_reference_and_amount(self):
        invoice = self._invoice(84.0, self.reference)
        # Same amount, other reference: not taken
        self._invoice(84.0, self._reference("7", "0106"))
        result = self.rule._apply_rules(self._payment(84.0), self.payer)
        self.assertEqual(result.get("amls"), self._receivable(invoice))
        self.assertTrue(result.get("auto_reconcile"))

    def test_exact_amount_several_items(self):
        invoices = self._invoice(84.0, self.reference) | self._invoice(
            84.0, self.reference
        )
        result = self.rule._apply_rules(self._payment(168.0), self.payer)
        self.assertEqual(result.get("amls"), self._receivable(invoices))

    def test_other_amount_rejected(self):
        self._invoice(84.0, self.reference)
        for amount in (50.0, 100.0):
            self.assertEqual(
                self.rule._apply_rules(self._payment(amount), self.payer), {}
            )

    def test_over_payment_allowed_without_option(self):
        invoice = self._invoice(84.0, self.reference)
        self.rule.exact_amount_only = False
        result = self.rule._apply_rules(self._payment(100.0), self.payer)
        self.assertEqual(result.get("amls"), self._receivable(invoice))

    def test_without_qr_reference_usual_matching(self):
        """A line without QR reference keeps the usual token matching"""
        invoice = self._invoice(84.0, "INV 736251904418")
        result = self.rule._apply_rules(
            self._payment(84.0, label="736251904418"), self.payer
        )
        self.assertEqual(result.get("amls"), self._receivable(invoice))

    def test_qr_type_rule_not_applicable(self):
        """A QR type rule only applies to its types, with a known partner and
        a product to book"""
        rule = self.env["account.reconcile.model"].create(
            {
                "name": "T3622 gifts",
                "rule_type": "writeoff_suggestion",
                "company_id": self.company.id,
                "qr_type_ids": [
                    Command.set(
                        self.env.ref("account_reconcile_compassion_ce.qr_type_1").ids
                    )
                ],
            }
        )
        # Type 7: not a gift
        self.assertFalse(rule._is_applicable_for(self._payment(84.0), self.payer))
        # Birthday gift of an unknown sponsorship: no product
        gift = self._payment(84.0, label=self._reference("1", "0000"))
        self.assertFalse(rule._is_applicable_for(gift, self.payer))
        # Not a QR reference at all
        other = self._payment(84.0, label="Thanks")
        self.assertFalse(rule._is_applicable_for(other, self.payer))
