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


class TestOffBalanceReconciliationUseCases(TransactionCase):
    """
    Comprehensive tests for off-balance reconciliation use cases.
    
    This test suite covers both direct reconciliation (bank transfer)
    and indirect reconciliation (Direct Debit with outstanding account).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["account.account"]
        cls.AccountMove = cls.env["account.move"]
        cls.AccountMoveLine = cls.env["account.move.line"]
        cls.Partner = cls.env["res.partner"]
        cls.Product = cls.env["product.product"]
        cls.Journal = cls.env["account.journal"]
        cls.company = cls.env.company

        # Create partner
        cls.partner = cls.Partner.create({
            "name": "Test Partner",
        })

        # Create products
        cls.product1 = cls.Product.create({
            "name": "Product 1",
            "type": "service",
        })
        cls.product2 = cls.Product.create({
            "name": "Product 2",
            "type": "service",
        })

        # Create accounts
        cls.receivable_account = cls.Account.create({
            "name": "Receivable Account",
            "code": "REC100",
            "account_type": "asset_receivable",
            "company_id": cls.company.id,
            "reconcile": True,
        })

        cls.on_balance_income_account = cls.Account.create({
            "name": "On-Balance Income",
            "code": "INC100",
            "account_type": "income",
            "company_id": cls.company.id,
        })

        cls.off_balance_income_account = cls.Account.create({
            "name": "Off-Balance Income",
            "code": "INCX100",
            "account_type": "income",
            "is_off_balance": True,
            "on_balance_account_id": cls.on_balance_income_account.id,
            "company_id": cls.company.id,
        })

        cls.off_balance_asset_account = cls.Account.create({
            "name": "Off-Balance Asset",
            "code": "ASSX100",
            "account_type": "asset_current",
            "is_off_balance": True,
            "company_id": cls.company.id,
        })

        cls.bank_account = cls.Account.create({
            "name": "Bank Account",
            "code": "BANK100",
            "account_type": "asset_cash",
            "company_id": cls.company.id,
            "reconcile": True,
        })

        cls.outstanding_account = cls.Account.create({
            "name": "Outstanding Account",
            "code": "OUT100",
            "account_type": "asset_current",
            "company_id": cls.company.id,
            "reconcile": True,
        })

        # Set the off-balance asset account on company
        cls.company.off_balance_asset_account_id = cls.off_balance_asset_account

        # Update partner's receivable account
        cls.partner.property_account_receivable_id = cls.receivable_account

        # Create journals
        cls.invoice_journal = cls.Journal.create({
            "name": "Customer Invoices",
            "code": "INV",
            "type": "sale",
            "company_id": cls.company.id,
        })

        cls.bank_journal = cls.Journal.create({
            "name": "Bank",
            "code": "BNK",
            "type": "bank",
            "company_id": cls.company.id,
        })

        cls.misc_journal = cls.Journal.create({
            "name": "Miscellaneous",
            "code": "MISC",
            "type": "general",
            "company_id": cls.company.id,
        })

    def _create_invoice(self, amount, product=None, account=None):
        """Helper method to create an invoice with off-balance account."""
        if product is None:
            product = self.product1
        if account is None:
            account = self.off_balance_income_account

        invoice = self.AccountMove.create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "journal_id": self.invoice_journal.id,
            "invoice_line_ids": [
                (0, 0, {
                    "name": "Invoice Line",
                    "product_id": product.id,
                    "quantity": 1,
                    "price_unit": amount,
                    "account_id": account.id,
                })
            ],
        })
        invoice.action_post()
        return invoice

    def _create_payment(self, amount, partner=None):
        """Helper method to create a bank payment entry."""
        if partner is None:
            partner = self.partner

        payment = self.AccountMove.create({
            "move_type": "entry",
            "journal_id": self.bank_journal.id,
            "partner_id": partner.id,
            "line_ids": [
                (0, 0, {
                    "name": "Bank Payment",
                    "account_id": self.bank_account.id,
                    "debit": amount,
                    "credit": 0.0,
                    "partner_id": partner.id,
                }),
                (0, 0, {
                    "name": "Receivable",
                    "account_id": self.receivable_account.id,
                    "debit": 0.0,
                    "credit": amount,
                    "partner_id": partner.id,
                }),
            ],
        })
        payment.action_post()
        return payment

    def _create_debit_order(self, amount, partner=None):
        """Helper method to create a debit order with outstanding account."""
        if partner is None:
            partner = self.partner

        debit_order = self.AccountMove.create({
            "move_type": "entry",
            "journal_id": self.misc_journal.id,
            "partner_id": partner.id,
            "line_ids": [
                (0, 0, {
                    "name": "Outstanding Debit",
                    "account_id": self.outstanding_account.id,
                    "debit": amount,
                    "credit": 0.0,
                    "partner_id": partner.id,
                }),
                (0, 0, {
                    "name": "Receivable",
                    "account_id": self.receivable_account.id,
                    "debit": 0.0,
                    "credit": amount,
                    "partner_id": partner.id,
                }),
            ],
        })
        debit_order.action_post()
        return debit_order

    def _create_outstanding_payment(self, amount, partner=None):
        """Helper method to create a payment on outstanding account."""
        if partner is None:
            partner = self.partner

        payment = self.AccountMove.create({
            "move_type": "entry",
            "journal_id": self.bank_journal.id,
            "partner_id": partner.id,
            "line_ids": [
                (0, 0, {
                    "name": "Bank Payment",
                    "account_id": self.bank_account.id,
                    "debit": amount,
                    "credit": 0.0,
                    "partner_id": partner.id,
                }),
                (0, 0, {
                    "name": "Outstanding",
                    "account_id": self.outstanding_account.id,
                    "debit": 0.0,
                    "credit": amount,
                    "partner_id": partner.id,
                }),
            ],
        })
        payment.action_post()
        return payment

    def _reconcile_lines(self, lines):
        """Helper method to reconcile account move lines."""
        lines.reconcile()

    def _get_off_balance_generated_lines(self, move):
        """Helper method to get off-balance generated lines from a move."""
        return move.line_ids.filtered("is_off_balance_generated")

    def _assert_off_balance_lines_created(self, payment, expected_count):
        """Assert that off-balance lines were created."""
        off_balance_lines = self._get_off_balance_generated_lines(payment)
        self.assertEqual(
            len(off_balance_lines),
            expected_count,
            f"Expected {expected_count} off-balance lines, got {len(off_balance_lines)}"
        )
        return off_balance_lines

    # Direct Reconciliation Tests (Bank Transfer)

    def test_direct_one_payment_one_invoice(self):
        """Test: One payment matching an existing invoice (direct reconciliation)."""
        # Create invoice
        invoice = self._create_invoice(100.0)
        
        # Create payment
        payment = self._create_payment(100.0)
        
        # Reconcile
        invoice_line = invoice.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        payment_line = payment.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice_line | payment_line)
        
        # Assert off-balance lines were created
        # Expected: 1 on-balance income line + 1 off-balance asset line = 2 lines
        off_balance_lines = self._assert_off_balance_lines_created(payment, 2)
        
        # Verify the on-balance income line
        on_balance_line = off_balance_lines.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(len(on_balance_line), 1)
        self.assertEqual(on_balance_line.balance, -100.0)
        
        # Verify the off-balance asset line
        asset_line = off_balance_lines.filtered(
            lambda l: l.account_id == self.off_balance_asset_account
        )
        self.assertEqual(len(asset_line), 1)
        self.assertEqual(asset_line.balance, 100.0)

    def test_direct_one_payment_with_additional_amount(self):
        """Test: One payment with additional amount unreconciled (direct reconciliation)."""
        # Create invoice
        invoice = self._create_invoice(100.0)
        
        # Create payment with extra amount
        payment = self._create_payment(150.0)
        
        # Reconcile only the invoice amount
        invoice_line = invoice.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        payment_line = payment.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice_line | payment_line)
        
        # Assert off-balance lines were created for the reconciled amount
        off_balance_lines = self._assert_off_balance_lines_created(payment, 2)
        
        # Verify the on-balance income line reflects only the reconciled amount
        on_balance_line = off_balance_lines.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line.balance, -100.0)
        
        # Verify payment line still has unreconciled amount
        self.assertEqual(payment_line.amount_residual, 50.0)

    def test_direct_multiple_payments_one_invoice(self):
        """Test: Multiple payments reconciling an existing invoice (direct reconciliation)."""
        # Create invoice
        invoice = self._create_invoice(100.0)
        
        # Create first partial payment
        payment1 = self._create_payment(60.0)
        
        # Reconcile first payment
        invoice_line = invoice.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        payment1_line = payment1.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice_line | payment1_line)
        
        # Assert first off-balance lines
        off_balance_lines1 = self._assert_off_balance_lines_created(payment1, 2)
        on_balance_line1 = off_balance_lines1.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line1.balance, -60.0)
        
        # Create second payment
        payment2 = self._create_payment(40.0)
        
        # Reconcile second payment
        payment2_line = payment2.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice_line | payment2_line)
        
        # Assert second off-balance lines
        off_balance_lines2 = self._assert_off_balance_lines_created(payment2, 2)
        on_balance_line2 = off_balance_lines2.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line2.balance, -40.0)
        
        # Verify invoice is fully reconciled
        self.assertEqual(invoice_line.amount_residual, 0.0)

    def test_direct_one_payment_multiple_invoices(self):
        """Test: One payment paying multiple invoices (direct reconciliation)."""
        # Create two invoices
        invoice1 = self._create_invoice(60.0, product=self.product1)
        invoice2 = self._create_invoice(40.0, product=self.product2)
        
        # Create payment
        payment = self._create_payment(100.0)
        
        # Reconcile payment with both invoices
        invoice1_line = invoice1.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        invoice2_line = invoice2.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        payment_line = payment.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice1_line | invoice2_line | payment_line)
        
        # Assert off-balance lines were created
        # Expected: 2 on-balance income lines (one per product) + 1 off-balance asset line = 3 lines
        off_balance_lines = self._assert_off_balance_lines_created(payment, 3)
        
        # Verify on-balance income lines for each product
        on_balance_lines = off_balance_lines.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(len(on_balance_lines), 2)
        
        # Verify total on-balance amount
        total_on_balance = sum(on_balance_lines.mapped("balance"))
        self.assertEqual(total_on_balance, -100.0)
        
        # Verify off-balance asset line
        asset_line = off_balance_lines.filtered(
            lambda l: l.account_id == self.off_balance_asset_account
        )
        self.assertEqual(asset_line.balance, 100.0)

    def test_direct_multiple_payments_multiple_invoices(self):
        """Test: Multiple payments reconciling multiple invoices with partial reconciles (direct)."""
        # Create two invoices
        invoice1 = self._create_invoice(100.0, product=self.product1)
        invoice2 = self._create_invoice(150.0, product=self.product2)
        
        # Create first payment - partially pays invoice1
        payment1 = self._create_payment(60.0)
        invoice1_line = invoice1.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        payment1_line = payment1.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice1_line | payment1_line)
        
        # Assert first off-balance lines
        off_balance_lines1 = self._assert_off_balance_lines_created(payment1, 2)
        on_balance_line1 = off_balance_lines1.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line1.balance, -60.0)
        
        # Create second payment - completes invoice1 and partially pays invoice2
        payment2 = self._create_payment(140.0)
        invoice2_line = invoice2.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        payment2_line = payment2.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice1_line | invoice2_line | payment2_line)
        
        # Assert second off-balance lines
        # Should have lines for both products
        off_balance_lines2 = self._assert_off_balance_lines_created(payment2, 3)
        
        # Create third payment - completes invoice2
        payment3 = self._create_payment(10.0)
        payment3_line = payment3.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice2_line | payment3_line)
        
        # Assert third off-balance lines
        off_balance_lines3 = self._assert_off_balance_lines_created(payment3, 2)
        on_balance_line3 = off_balance_lines3.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line3.balance, -10.0)
        
        # Verify both invoices are fully reconciled
        self.assertEqual(invoice1_line.amount_residual, 0.0)
        self.assertEqual(invoice2_line.amount_residual, 0.0)

    # Indirect Reconciliation Tests (Direct Debit with Outstanding Account)

    def test_indirect_one_payment_one_invoice(self):
        """Test: One payment matching an existing invoice (indirect via debit order)."""
        # Create invoice
        invoice = self._create_invoice(100.0)
        
        # Create debit order
        debit_order = self._create_debit_order(100.0)
        
        # Reconcile invoice with debit order
        invoice_line = invoice.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        debit_line = debit_order.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice_line | debit_line)
        
        # Create payment on outstanding account
        payment = self._create_outstanding_payment(100.0)
        
        # Reconcile payment with debit order outstanding
        debit_outstanding_line = debit_order.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        payment_outstanding_line = payment.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        self._reconcile_lines(debit_outstanding_line | payment_outstanding_line)
        
        # Assert off-balance lines were created on the payment
        off_balance_lines = self._assert_off_balance_lines_created(payment, 2)
        
        # Verify the on-balance income line
        on_balance_line = off_balance_lines.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(len(on_balance_line), 1)
        self.assertEqual(on_balance_line.balance, -100.0)

    def test_indirect_one_payment_with_additional_amount(self):
        """Test: One payment with additional unreconciled amount (indirect via debit order)."""
        # Create invoice
        invoice = self._create_invoice(100.0)
        
        # Create debit order
        debit_order = self._create_debit_order(100.0)
        
        # Reconcile invoice with debit order
        invoice_line = invoice.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        debit_line = debit_order.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice_line | debit_line)
        
        # Create payment with extra amount
        payment = self._create_outstanding_payment(150.0)
        
        # Reconcile payment with debit order outstanding
        debit_outstanding_line = debit_order.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        payment_outstanding_line = payment.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        self._reconcile_lines(debit_outstanding_line | payment_outstanding_line)
        
        # Assert off-balance lines were created for the reconciled amount
        off_balance_lines = self._assert_off_balance_lines_created(payment, 2)
        
        # Verify the on-balance income line reflects only the reconciled amount
        on_balance_line = off_balance_lines.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line.balance, -100.0)
        
        # Verify payment line still has unreconciled amount
        self.assertEqual(payment_outstanding_line.amount_residual, 50.0)

    def test_indirect_multiple_payments_one_invoice(self):
        """Test: Multiple payments reconciling one invoice (indirect via debit order)."""
        # Create invoice
        invoice = self._create_invoice(100.0)
        
        # Create debit order
        debit_order = self._create_debit_order(100.0)
        
        # Reconcile invoice with debit order
        invoice_line = invoice.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        debit_line = debit_order.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice_line | debit_line)
        
        # Create first partial payment
        payment1 = self._create_outstanding_payment(60.0)
        
        # Reconcile first payment
        debit_outstanding_line = debit_order.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        payment1_outstanding_line = payment1.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        self._reconcile_lines(debit_outstanding_line | payment1_outstanding_line)
        
        # Assert first off-balance lines
        off_balance_lines1 = self._assert_off_balance_lines_created(payment1, 2)
        on_balance_line1 = off_balance_lines1.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line1.balance, -60.0)
        
        # Create second payment
        payment2 = self._create_outstanding_payment(40.0)
        
        # Reconcile second payment
        payment2_outstanding_line = payment2.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        self._reconcile_lines(debit_outstanding_line | payment2_outstanding_line)
        
        # Assert second off-balance lines
        off_balance_lines2 = self._assert_off_balance_lines_created(payment2, 2)
        on_balance_line2 = off_balance_lines2.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line2.balance, -40.0)
        
        # Verify debit order outstanding is fully reconciled
        self.assertEqual(debit_outstanding_line.amount_residual, 0.0)

    def test_indirect_one_payment_multiple_invoices(self):
        """Test: One payment paying multiple invoices (indirect via debit order)."""
        # Create two invoices
        invoice1 = self._create_invoice(60.0, product=self.product1)
        invoice2 = self._create_invoice(40.0, product=self.product2)
        
        # Create debit orders for each invoice
        debit_order1 = self._create_debit_order(60.0)
        debit_order2 = self._create_debit_order(40.0)
        
        # Reconcile invoices with debit orders
        invoice1_line = invoice1.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        debit1_line = debit_order1.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice1_line | debit1_line)
        
        invoice2_line = invoice2.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        debit2_line = debit_order2.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice2_line | debit2_line)
        
        # Create payment
        payment = self._create_outstanding_payment(100.0)
        
        # Reconcile payment with both debit order outstanding lines
        debit1_outstanding_line = debit_order1.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        debit2_outstanding_line = debit_order2.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        payment_outstanding_line = payment.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        self._reconcile_lines(
            debit1_outstanding_line | debit2_outstanding_line | payment_outstanding_line
        )
        
        # Assert off-balance lines were created
        off_balance_lines = self._assert_off_balance_lines_created(payment, 3)
        
        # Verify on-balance income lines for each product
        on_balance_lines = off_balance_lines.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(len(on_balance_lines), 2)
        
        # Verify total on-balance amount
        total_on_balance = sum(on_balance_lines.mapped("balance"))
        self.assertEqual(total_on_balance, -100.0)

    def test_indirect_multiple_payments_multiple_invoices(self):
        """Test: Multiple payments reconciling multiple invoices with partial reconciles (indirect)."""
        # Create two invoices
        invoice1 = self._create_invoice(100.0, product=self.product1)
        invoice2 = self._create_invoice(150.0, product=self.product2)
        
        # Create debit orders for each invoice
        debit_order1 = self._create_debit_order(100.0)
        debit_order2 = self._create_debit_order(150.0)
        
        # Reconcile invoices with debit orders
        invoice1_line = invoice1.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        debit1_line = debit_order1.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice1_line | debit1_line)
        
        invoice2_line = invoice2.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        debit2_line = debit_order2.line_ids.filtered(
            lambda l: l.account_id == self.receivable_account
        )
        self._reconcile_lines(invoice2_line | debit2_line)
        
        # Create first payment - partially pays debit order 1
        payment1 = self._create_outstanding_payment(60.0)
        debit1_outstanding_line = debit_order1.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        payment1_outstanding_line = payment1.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        self._reconcile_lines(debit1_outstanding_line | payment1_outstanding_line)
        
        # Assert first off-balance lines
        off_balance_lines1 = self._assert_off_balance_lines_created(payment1, 2)
        on_balance_line1 = off_balance_lines1.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line1.balance, -60.0)
        
        # Create second payment - completes debit order 1 and partially pays debit order 2
        payment2 = self._create_outstanding_payment(140.0)
        debit2_outstanding_line = debit_order2.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        payment2_outstanding_line = payment2.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        self._reconcile_lines(
            debit1_outstanding_line | debit2_outstanding_line | payment2_outstanding_line
        )
        
        # Assert second off-balance lines
        off_balance_lines2 = self._assert_off_balance_lines_created(payment2, 3)
        
        # Create third payment - completes debit order 2
        payment3 = self._create_outstanding_payment(10.0)
        payment3_outstanding_line = payment3.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account
        )
        self._reconcile_lines(debit2_outstanding_line | payment3_outstanding_line)
        
        # Assert third off-balance lines
        off_balance_lines3 = self._assert_off_balance_lines_created(payment3, 2)
        on_balance_line3 = off_balance_lines3.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(on_balance_line3.balance, -10.0)
        
        # Verify both debit orders are fully reconciled
        self.assertEqual(debit1_outstanding_line.amount_residual, 0.0)
        self.assertEqual(debit2_outstanding_line.amount_residual, 0.0)
