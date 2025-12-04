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
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.base.tests.common import DISABLED_MAIL_CONTEXT
from odoo.tests import tagged


@tagged("-at_install", "post_install")
class TestOffBalanceReconciliationUseCases(AccountTestInvoicingCommon):
    """
    Comprehensive tests for off-balance reconciliation use cases.

    This test suite covers both direct reconciliation (bank transfer)
    and indirect reconciliation (Direct Debit with outstanding account).
    """

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.env = cls.env(context=dict(cls.env.context, **DISABLED_MAIL_CONTEXT))
        cls.Account = cls.env["account.account"]
        cls.AccountMove = cls.env["account.move"]
        cls.AccountMoveLine = cls.env["account.move.line"]
        cls.Partner = cls.env["res.partner"]
        cls.Product = cls.env["product.product"]
        cls.Journal = cls.env["account.journal"]
        cls.company = cls.env.company

        # Setup off-balance products, accounts and journals
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.receivable_account = cls.company_data["default_account_receivable"]
        cls.receivable_offbalance = cls.copy_account(cls.receivable_account, {
            "is_off_balance": True,
            "on_balance_account_id": cls.receivable_account.id
        })
        cls.on_balance_income_account = cls.company_data["default_account_revenue"]
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
        cls.bank_account = cls.bank_journal.default_account_id

        cls.outstanding_account = cls.copy_account(
            cls.company.account_journal_payment_debit_account_id)

        # Set the off-balance asset account on company
        cls.company.off_balance_asset_account_id = cls.off_balance_asset_account

        # Update partner's and products accounts
        cls.partner_a.property_account_receivable_id = cls.receivable_offbalance
        cls.product_o = cls.env['product.product'].create({
            'name': 'product_o',
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
            'uom_po_id': cls.env.ref('uom.product_uom_unit').id,
            'lst_price': 1000.0,
            'property_account_income_id': cls.off_balance_income_account.id,
            'property_account_expense_id': cls.company_data[
                'default_account_expense'].id,
            'taxes_id': False,
        })

    def _create_payment(self, amount, partner=None):
        """
        Helper method to create a bank payment entry.

        :param amount: Payment amount (float)
        :param partner: Partner for the payment (default: self.partner)
        :return: Posted payment move (account.move)
        """
        if partner is None:
            partner = self.partner_a

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
                    "account_id": self.receivable_offbalance.id,
                    "debit": 0.0,
                    "credit": amount,
                    "partner_id": partner.id,
                }),
            ],
        })
        payment.action_post()
        return payment

    def _create_debit_order(self, amount, partner=None):
        """
        Helper method to create a debit order with outstanding account.

        :param amount: Debit order amount (float)
        :param partner: Partner for the debit order (default: self.partner)
        :return: Posted debit order move (account.move)
        """
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
        """
        Helper method to create a payment on outstanding account.

        :param amount: Payment amount (float)
        :param partner: Partner for the payment (default: self.partner)
        :return: Posted payment move (account.move)
        """
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

    def _get_off_balance_generated_lines(self, move):
        """
        Helper method to get off-balance generated lines from a move.

        :param move: Account move to check (account.move)
        :return: Filtered lines with is_off_balance_generated=True (account.move.line recordset)
        """
        return move.line_ids.filtered("is_off_balance_generated")

    def _assert_off_balance_lines_created(self, payment, expected_count):
        """
        Assert that off-balance lines were created.

        :param payment: Payment move to check (account.move)
        :param expected_count: Expected number of off-balance generated lines (int)
        :return: Off-balance generated lines (account.move.line recordset)
        """
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
        amount_total = self.product_o.list_price
        invoice = self.init_invoice("out_invoice", post=True, products=[self.product_o])

        # Create payment
        payment = self._create_payment(amount_total)

        # Reconcile
        invoice_line = invoice.line_ids.filtered(
            lambda l: l.account_id == self.receivable_offbalance
        )
        payment_line = payment.line_ids.filtered(
            lambda l: l.account_id == self.receivable_offbalance
        )
        (invoice_line | payment_line).reconcile()

        # Assert off-balance lines were created
        # Expected: 1 on-balance income line + 1 off-balance asset line = 2 lines
        generated_lines = self._assert_off_balance_lines_created(payment, 2)

        # Verify the on-balance income line
        on_balance_line = generated_lines.filtered(
            lambda l: l.account_id == self.on_balance_income_account
        )
        self.assertEqual(len(on_balance_line), 1)
        self.assertAlmostEqual(on_balance_line.balance, -amount_total, places=2)

        # Verify the off-balance asset line
        asset_line = generated_lines.filtered(
            lambda l: l.account_id == self.off_balance_asset_account
        )
        self.assertEqual(len(asset_line), 1)
        self.assertAlmostEqual(asset_line.balance, amount_total, places=2)

    def _test_direct_one_payment_with_additional_amount(self):
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

    def _test_direct_multiple_payments_one_invoice(self):
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

    def _test_direct_one_payment_multiple_invoices(self):
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

    def _test_direct_multiple_payments_multiple_invoices(self):
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

    def _test_indirect_one_payment_one_invoice(self):
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

    def _test_indirect_one_payment_with_additional_amount(self):
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

    def _test_indirect_multiple_payments_one_invoice(self):
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

    def _test_indirect_one_payment_multiple_invoices(self):
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

    def _test_indirect_multiple_payments_multiple_invoices(self):
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
