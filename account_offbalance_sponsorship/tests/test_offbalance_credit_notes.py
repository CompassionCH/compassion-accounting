from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("-at_install", "post_install")
class TestOffBalanceCreditNotes(AccountTestInvoicingCommon):
    """
    Tests for off-balance credit note reconciliation.

    This test suite covers credit note reconciliation scenarios
    to ensure that off-balance lines are properly reversed.
    """

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.Account = cls.env["account.account"]
        cls.AccountMove = cls.env["account.move"]
        cls.AccountMoveLine = cls.env["account.move.line"]
        cls.company = cls.env.company

        # Setup off-balance accounts
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.receivable_account = cls.company_data["default_account_receivable"]
        cls.receivable_offbalance = cls.copy_account(
            cls.receivable_account,
            {
                "is_off_balance": True,
                "on_balance_account_id": cls.receivable_account.id,
            },
        )
        cls.on_balance_income_account = cls.company_data["default_account_revenue"]
        cls.off_balance_income_account = cls.Account.create(
            {
                "name": "Off-Balance Income",
                "code": "INCXCN100",
                "account_type": "income",
                "is_off_balance": True,
                "on_balance_account_id": cls.on_balance_income_account.id,
                "company_id": cls.company.id,
            }
        )
        cls.off_balance_asset_account = cls.Account.create(
            {
                "name": "Off-Balance Asset",
                "code": "ASSXCN100",
                "account_type": "asset_current",
                "is_off_balance": True,
                "company_id": cls.company.id,
            }
        )
        cls.bank_account = cls.bank_journal.default_account_id

        # Set the off-balance asset account on company
        cls.company.off_balance_asset_account_id = cls.off_balance_asset_account

        # Update partner's account to use off-balance receivable
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
        cls.currency = cls.company.currency_id

    def _create_payment(self, amount, partner=None):
        """
        Helper method to create a bank payment entry.

        :param amount: Payment amount (float)
        :param partner: Partner for the payment (default: self.partner_a)
        :return: Posted payment move (account.move)
        """
        if partner is None:
            partner = self.partner_a

        payment = self.AccountMove.create(
            {
                "move_type": "entry",
                "journal_id": self.bank_journal.id,
                "partner_id": partner.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Bank Payment",
                            "account_id": self.bank_account.id,
                            "debit": amount,
                            "credit": 0.0,
                            "partner_id": partner.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Receivable",
                            "account_id": self.receivable_offbalance.id,
                            "debit": 0.0,
                            "credit": amount,
                            "partner_id": partner.id,
                        },
                    ),
                ],
            }
        )
        payment.action_post()
        return payment

    def _receivable_lines(self, moves):
        """Return the receivable/off-balance lines for the provided moves."""
        return moves.line_ids.filtered(
            lambda mvl: mvl.account_id == self.receivable_offbalance
        )

    def test_invoice_reconciliation_creates_offbalance_lines(self):
        """
        Test that reconciling an invoice creates off-balance lines.

        Steps:
        1. Create and post an invoice with off-balance income account
        2. Create a payment
        3. Reconcile invoice and payment
        4. Verify that off-balance lines are created (on-balance income + asset)
        """
        # Step 1: Create invoice
        invoice = self.init_invoice(
            "out_invoice", post=True, products=[self.product_off_balance]
        )
        invoice_amount = invoice.amount_total

        # Step 2: Create payment
        payment = self._create_payment(invoice_amount)

        # Step 3: Reconcile
        (self._receivable_lines(invoice) | self._receivable_lines(payment)).reconcile()

        # Step 4: Assert off-balance lines are created
        generated_lines = payment.line_ids.filtered("is_off_balance_generated")
        self.assertEqual(
            len(generated_lines),
            2,
            "Expected 2 off-balance lines (on-balance income + asset)",
        )

        # Verify on-balance income line
        on_balance_income = generated_lines.filtered(
            lambda mvl: mvl.account_id == self.on_balance_income_account
        )
        self.assertEqual(len(on_balance_income), 1)
        self.assertAlmostEqual(
            on_balance_income.balance, -invoice_amount, places=2
        )

        # Verify off-balance asset line
        asset_line = generated_lines.filtered(
            lambda mvl: mvl.account_id == self.off_balance_asset_account
        )
        self.assertEqual(len(asset_line), 1)
        self.assertAlmostEqual(asset_line.balance, invoice_amount, places=2)

    def test_credit_note_reconciliation_reverses_offbalance_lines(self):
        """
        Test that reconciling a credit note creates reversed off-balance lines.

        Steps:
        1. Create and post an invoice with off-balance income account
        2. Create a payment and reconcile with invoice
        3. Verify off-balance lines are created
        4. Create a credit note (out_refund) for the same amount
        5. Create a refund payment
        6. Reconcile credit note with refund payment
        7. Verify that reversed off-balance lines are created
        """
        # Step 1: Create invoice
        invoice = self.init_invoice(
            "out_invoice", post=True, products=[self.product_off_balance]
        )
        invoice_amount = invoice.amount_total

        # Step 2: Create payment and reconcile
        payment = self._create_payment(invoice_amount)
        (self._receivable_lines(invoice) | self._receivable_lines(payment)).reconcile()

        # Step 3: Verify off-balance lines created
        invoice_generated_lines = payment.line_ids.filtered("is_off_balance_generated")
        self.assertEqual(len(invoice_generated_lines), 2)

        # Step 4: Create credit note
        credit_note = self.init_invoice(
            "out_refund", post=True, products=[self.product_off_balance]
        )
        credit_note_amount = credit_note.amount_total

        # Verify amounts match
        self.assertAlmostEqual(invoice_amount, credit_note_amount, places=2)

        # Step 5: Create refund payment (reverse direction)
        refund_payment = self.AccountMove.create(
            {
                "move_type": "entry",
                "journal_id": self.bank_journal.id,
                "partner_id": self.partner_a.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Bank Refund",
                            "account_id": self.bank_account.id,
                            "debit": 0.0,
                            "credit": credit_note_amount,
                            "partner_id": self.partner_a.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Receivable Refund",
                            "account_id": self.receivable_offbalance.id,
                            "debit": credit_note_amount,
                            "credit": 0.0,
                            "partner_id": self.partner_a.id,
                        },
                    ),
                ],
            }
        )
        refund_payment.action_post()

        # Step 6: Reconcile credit note with refund payment
        (
            self._receivable_lines(credit_note)
            | self._receivable_lines(refund_payment)
        ).reconcile()

        # Step 7: Verify reversed off-balance lines are created
        credit_note_generated_lines = refund_payment.line_ids.filtered(
            "is_off_balance_generated"
        )
        self.assertEqual(
            len(credit_note_generated_lines),
            2,
            "Expected 2 reversed off-balance lines for credit note",
        )

        # Verify reversed on-balance income line (positive for credit note)
        cn_on_balance_income = credit_note_generated_lines.filtered(
            lambda mvl: mvl.account_id == self.on_balance_income_account
        )
        self.assertEqual(len(cn_on_balance_income), 1)
        self.assertAlmostEqual(
            cn_on_balance_income.balance, credit_note_amount, places=2
        )

        # Verify reversed off-balance asset line (negative for credit note)
        cn_asset_line = credit_note_generated_lines.filtered(
            lambda mvl: mvl.account_id == self.off_balance_asset_account
        )
        self.assertEqual(len(cn_asset_line), 1)
        self.assertAlmostEqual(cn_asset_line.balance, -credit_note_amount, places=2)

        # Verify that the net effect cancels out
        total_on_balance_income = (
            invoice_generated_lines.filtered(
                lambda mvl: mvl.account_id == self.on_balance_income_account
            ).balance
            + cn_on_balance_income.balance
        )
        total_asset = (
            invoice_generated_lines.filtered(
                lambda mvl: mvl.account_id == self.off_balance_asset_account
            ).balance
            + cn_asset_line.balance
        )
        self.assertAlmostEqual(
            total_on_balance_income, 0.0, places=2, msg="Net income should be zero"
        )
        self.assertAlmostEqual(
            total_asset, 0.0, places=2, msg="Net asset should be zero"
        )
