from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.tools import mod10r


@tagged("post_install", "-at_install")
class TestReconcileProposal(TransactionCase):
    """T3692 A rule without Label/Note/Reference option proposes nothing for
    a gift QR payment, and otherwise only an open item of the same amount."""

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
        cls.payer = cls.env["res.partner"].create({"name": "T3692 Payer"})
        cls.receivable_account = cls.payer.with_company(
            cls.company
        ).property_account_receivable_id
        rule_obj = cls.env["account.reconcile.model"]
        # Only the rules of the test decide what is proposed
        rule_obj.search(
            [
                ("rule_type", "in", ["invoice_matching", "writeoff_suggestion"]),
                ("company_id", "=", cls.company.id),
            ]
        ).active = False
        cls.reference_rule = rule_obj.create(
            {
                "name": "T3692 reference",
                "rule_type": "invoice_matching",
                "match_text_location_label": True,
                "match_text_location_reference": True,
                "auto_reconcile": False,
                "past_months_limit": 0,
                "sequence": 1,
                "company_id": cls.company.id,
            }
        )
        cls.proposal_rule = rule_obj.create(
            {
                "name": "T3692 proposal",
                "rule_type": "invoice_matching",
                "match_text_location_label": False,
                "match_text_location_note": False,
                "match_text_location_reference": False,
                "unique_matching": False,
                "past_months_limit": 0,
                "sequence": 2,
                "company_id": cls.company.id,
            }
        )

    def _open_item(self, partner, amount, date, ref="T3692 item"):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.misc_journal.id,
                "date": date,
                "ref": ref,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": self.receivable_account.id,
                            "partner_id": partner.id,
                            "name": ref,
                            "debit": amount,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": self.income_account.id,
                            "partner_id": partner.id,
                            "name": "T3692 income",
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

    def _payment(self, partner, amount, label="Thanks", ref=False):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "date": fields.Date.today(),
                "amount": amount,
                "payment_ref": label,
                "ref": ref,
                "partner_id": partner.id,
            }
        )

    def _rules(self):
        return self.reference_rule | self.proposal_rule

    def test_gift_qr_reference_no_proposal(self):
        """A gift QR payment gets no invoice proposed, even of the same amount"""
        today = fields.Date.today()
        self._open_item(self.payer, 50.0, today)
        self._open_item(self.payer, 100.0, today)
        st_line = self._payment(
            self.payer,
            100.0,
            label="Family gift",
            ref="000000000155165600001300000",
        )
        self.assertFalse(
            self.proposal_rule._get_invoice_matching_proposal_candidates(
                st_line, self.payer
            )
        )
        self.assertEqual(self._rules()._apply_rules(st_line, self.payer), {})

    def test_proposal_same_amount(self):
        """Without reference, only an open item of the same amount is proposed"""
        today = fields.Date.today()
        self._open_item(self.payer, 50.0, today.replace(day=1))
        same_amount = self._open_item(self.payer, 100.0, today)
        st_line = self._payment(self.payer, 100.0)
        result = self._rules()._apply_rules(st_line, self.payer)
        self.assertEqual(result.get("model"), self.proposal_rule)
        self.assertEqual(result.get("amls"), same_amount)
        self.assertFalse(result.get("auto_reconcile"))

    def test_no_proposal_other_amount(self):
        """Without reference, nothing is proposed when no amount is the same"""
        self._open_item(self.payer, 50.0, fields.Date.today())
        st_line = self._payment(self.payer, 100.0)
        self.assertEqual(self._rules()._apply_rules(st_line, self.payer), {})

    def test_reference_match_unchanged(self):
        """A matching reference still finds the item, whatever its amount"""
        item = self._open_item(
            self.payer, 50.0, fields.Date.today(), ref="REF 736251904418"
        )
        st_line = self._payment(self.payer, 100.0, ref="736251904418")
        result = self._rules()._apply_rules(st_line, self.payer)
        self.assertEqual(result.get("model"), self.reference_rule)
        self.assertEqual(result.get("amls"), item)

    def test_gift_qr_prefills_gift_button(self):
        """A gift QR payment of a sponsor with an open invoice opens with the
        gift button of its gift type, not with the invoice"""
        contracts = self.env["recurring.contract"].search(
            [
                ("state", "=", "active"),
                ("child_id", "!=", False),
                ("company_id", "=", self.company.id),
                ("commitment_number", ">", 0),
                ("partner_id.ref", "!=", False),
            ],
            limit=50,
        )
        gift_type = self.env["sponsorship.gift.type"].browse(1)
        gift_rule = self.env["account.reconcile.model"].search(
            [
                ("rule_type", "=", "writeoff_button"),
                ("company_id", "=", self.company.id),
                (
                    "line_ids.product_id.product_tmpl_id",
                    "=",
                    gift_type.exists().product_id.id,
                ),
            ],
            limit=1,
        )
        if not gift_rule:
            self.skipTest("No gift button for birthday gifts")
        for contract in contracts:
            partner = contract.gift_partner_id
            if not (partner.ref or "").isdigit():
                continue
            reference = mod10r(
                f"000000000{partner.ref.zfill(7)}"
                f"{str(contract.commitment_number).zfill(5)}10000"
            )
            # Larger than the sponsor's open items: they would all be proposed
            st_line = self._payment(
                partner, 10000.0, label="Birthday gift", ref=reference
            )
            if st_line._get_contract_from_reference() == contract:
                break
        else:
            self.skipTest("No sponsorship found from a gift QR reference")
        invoice_item = self._open_item(partner, 42.0, fields.Date.today())
        # T3622 The gift button is prefilled by the (manual) gift QR rule
        self.env["account.reconcile.model"].create(
            {
                "name": "T3622 QR gifts",
                "rule_type": "writeoff_suggestion",
                "auto_reconcile": False,
                "match_partner": True,
                "sequence": 1,
                "company_id": self.company.id,
                "qr_type_ids": [
                    (
                        6,
                        0,
                        self.env.ref("account_reconcile_compassion_ce.qr_type_1").ids,
                    )
                ],
            }
        )
        # Without option, the rule finds the sponsor's open items
        self.assertIn(
            invoice_item,
            self.proposal_rule._get_invoice_matching_amls_candidates(st_line, partner)[
                "amls"
            ],
        )
        data = st_line._default_reconcile_data()["data"]
        self.assertFalse(
            [line for line in data if line["kind"] == "other" and line.get("id")],
            "No open item is proposed for a gift QR payment",
        )
        gift_lines = [line for line in data if line["kind"] == "other"]
        self.assertEqual(len(gift_lines), 1)
        self.assertEqual(gift_lines[0]["contract_id"][0], contract.id)
        self.assertIn(gift_lines[0]["account_id"][0], gift_rule.line_ids.account_id.ids)
