from odoo import fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("-at_install", "post_install")
class TestOffBalanceReconciliationUseCases(AccountTestInvoicingCommon):
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
        cls.env.user.groups_id |= cls.env.ref(
            "account_payment_order.group_account_payment"
        )

        # Setup off-balance products, accounts and journals
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
                "code": "INCX100",
                "account_type": "income",
                "is_off_balance": True,
                "on_balance_account_id": cls.on_balance_income_account.id,
                "company_ids": [(4, cls.company.id)],
            }
        )
        cls.off_balance_asset_account = cls.Account.create(
            {
                "name": "Off-Balance Asset",
                "code": "ASSX100",
                "account_type": "asset_current",
                "is_off_balance": True,
                "company_ids": [(4, cls.company.id)],
            }
        )
        cls.bank_account = cls.bank_journal.default_account_id

        cls.outstanding_account = cls.env['account.chart.template'].ref('account_journal_payment_debit_account_id')

        # Set the off-balance asset account on company
        cls.company.off_balance_asset_account_id = cls.off_balance_asset_account

        # Update partner's and products accounts
        cls.partner_a.property_account_receivable_id = cls.receivable_offbalance
        cls.product_o = cls.env["product.product"].create(
            {
                "name": "product_o",
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
        cls.product_o_2 = cls.env["product.product"].create(
            {
                "name": "product_o_2",
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
                "uom_po_id": cls.env.ref("uom.product_uom_unit").id,
                "lst_price": 200.0,
                "property_account_income_id": cls.off_balance_income_account.id,
                "property_account_expense_id": cls.company_data[
                    "default_account_expense"
                ].id,
                "taxes_id": False,
            }
        )

        cls.inbound_mode = cls.env["account.payment.mode"].create(
            {
                "name": "Test Direct Debit of customers",
                "bank_account_link": "variable",
                "payment_method_id": cls.env.ref(
                    "account.account_payment_method_manual_in"
                ).id,
                "company_id": cls.company.id,
            }
        )
        cls.currency = cls.company.currency_id

    def _create_payment(
        self,
        amounts,
        partner=None,
        dst_account_id=None,
        currency=None,
        amounts_currency=None,
    ):
        """
        Helper method to create a bank payment entry.

        :param amounts: Payment amounts (floats)
        :param partner: Partner for the payment (default: self.partner)
        :param dst_account_id: Destination account for the payment
            (default: receivable_offbalance)
        :param currency: Currency of the payment (optional)
        :param amounts_currency: Amounts in currency (optional, must match amounts)
        :return: Posted payment move (account.move)
        """
        if partner is None:
            partner = self.partner_a

        receivable_lines = []
        for i, amount in enumerate(amounts):
            vals = {
                "name": "Receivable",
                "account_id": dst_account_id or self.receivable_offbalance.id,
                "debit": 0.0,
                "credit": amount,
                "partner_id": partner.id,
            }
            if currency and amounts_currency:
                vals.update(
                    {
                        "currency_id": currency.id,
                        "amount_currency": amounts_currency[i],
                    }
                )
            receivable_lines.append((0, 0, vals))

        bank_vals = {
            "name": "Bank Payment",
            "account_id": self.bank_account.id,
            "debit": sum(amounts),
            "credit": 0.0,
            "partner_id": partner.id,
        }
        if currency and amounts_currency:
            bank_vals.update(
                {
                    "currency_id": currency.id,
                    "amount_currency": -sum(amounts_currency),
                }
            )

        payment = self.AccountMove.create(
            {
                "move_type": "entry",
                "journal_id": self.bank_journal.id,
                "partner_id": partner.id,
                "line_ids": [
                    (0, 0, bank_vals),
                ]
                + receivable_lines,
            }
        )
        payment.action_post()
        return payment

    def _create_debit_order(self, invoices):
        """
        Helper method to create a debit order with outstanding account.

        :param invoices: Invoice to pay via debit order (account.move)
        :return: Posted debit order moves (account.move)
        """
        payment_order_id = invoices.create_account_payment_line()["res_id"]
        payment_order = self.env["account.payment.order"].browse(payment_order_id)
        payment_order.journal_id = self.bank_journal
        payment_order.draft2open()
        payment_order.generated2uploaded()
        return payment_order.move_ids

    def _assert_off_balance_lines_created(self, payment, expected_amount):
        """
        Assert that off-balance lines were created and sum to expected amount.

        :param payment: Payment move to check (account.move)
        :param expected_amount: Expected total amount of on-balance lines (float)
        :return: Off-balance generated lines (account.move.line recordset)
        """
        off_balance_lines = payment.line_ids.filtered("is_off_balance_generated")

        # Check on-balance income lines total
        on_balance = off_balance_lines.filtered(
            lambda mvl: mvl.account_id == self.on_balance_income_account
        )
        on_balance_total = sum(on_balance.mapped("credit"))
        self.assertAlmostEqual(on_balance_total, expected_amount, places=2)

        # Check asset lines total
        # The sum of income on_balance amounts (Credit)
        # must equal the sum of the asset lines (Debit)
        asset_lines = off_balance_lines.filtered(
            lambda mvl: mvl.account_id == self.off_balance_asset_account
        )
        self.assertAlmostEqual(
            sum(asset_lines.mapped("debit")), on_balance_total, places=2
        )
        return off_balance_lines

    def _receivable_lines(self, moves):
        """Return the receivable/off-balance lines for the provided moves."""
        return moves.line_ids.filtered(
            lambda mvl: mvl.account_id == self.receivable_offbalance
        )

    def _outstanding_lines(self, moves):
        """Return the outstanding-account lines for the provided moves."""
        return moves.line_ids.filtered(
            lambda mvl: mvl.account_id == self.outstanding_account
        )

    def _prepare_indirect_invoices(self, products):
        """
        Create invoices configured for indirect reconciliation
        and return the debit order.
        """
        invoices = self.env["account.move"]
        for product in products:
            invoice = self.init_invoice("out_invoice", products=[product], post=True)
            invoice.payment_mode_id = self.inbound_mode
            invoices |= invoice
        invoices = invoices.sorted(lambda inv: inv.id)
        debit_moves = self._create_debit_order(invoices)
        self.assertSetEqual(set(invoices.mapped("payment_state")), {"in_payment"})
        self._assert_off_balance_lines_created(debit_moves, 0.0)
        return invoices, debit_moves, self._outstanding_lines(debit_moves)

    # Direct Reconciliation Tests (Bank Transfer)

    def test_direct_one_payment_one_invoice(self):
        """Test: One payment matching an existing invoice (direct reconciliation)."""
        # Step 1: Prepare invoice and payment
        amount_total = self.product_o.list_price
        invoice = self.init_invoice("out_invoice", products=[self.product_o], post=True)
        payment = self._create_payment([amount_total])

        # Step 2: Reconcile receivable lines
        (self._receivable_lines(invoice) | self._receivable_lines(payment)).reconcile()

        # Step 3: Assert generated on/off balance effects
        self._assert_off_balance_lines_created(payment, amount_total)

    def test_direct_one_payment_with_additional_amount(self):
        """Test: One payment with additional amount unreconciled."""
        # Step 1: Prepare invoice and overpaid payment
        amount_total = self.product_o.list_price
        extra_amount = 150.0
        invoice = self.init_invoice("out_invoice", products=[self.product_o], post=True)
        payment = self._create_payment([amount_total, extra_amount])

        # Step 2: Reconcile only the invoice amount
        invoice_line = self._receivable_lines(invoice)
        payment_lines = self._receivable_lines(payment)
        invoice_payment_line = payment_lines.filtered(
            lambda mvl: self.currency.is_zero(mvl.credit - amount_total)
        )
        residual_line = payment_lines - invoice_payment_line
        (invoice_line | invoice_payment_line).reconcile()

        # Step 3: Assert generated lines cover only the reconciled part
        self._assert_off_balance_lines_created(payment, amount_total)
        self.assertAlmostEqual(invoice_payment_line.amount_residual, 0.0, places=2)
        self.assertAlmostEqual(residual_line.credit, extra_amount)

        # Step 4: Consume the residual via a new invoice (widget flow)
        self.product_o.list_price = extra_amount
        residual_invoice = self.init_invoice(
            "out_invoice", products=[self.product_o], post=True
        )
        self.assert_invoice_outstanding_to_reconcile_widget(
            residual_invoice, {payment.id: extra_amount}
        )
        residual_invoice.js_assign_outstanding_line(residual_line.id)
        self.assert_invoice_outstanding_reconciled_widget(
            residual_invoice, {payment.id: extra_amount}
        )

        # Step 5: Off-balance totals now cover both invoices
        self._assert_off_balance_lines_created(payment, amount_total + extra_amount)

    def test_direct_multiple_payments_one_invoice(self):
        """Test: Multiple payments reconciling an existing invoice."""
        # Step 1: Prepare invoice and split payments
        invoice = self.init_invoice("out_invoice", products=[self.product_o], post=True)
        amount_total = self.product_o.list_price
        payment_price = amount_total / 3.0
        payment1 = self._create_payment([payment_price])
        payment2 = self._create_payment([amount_total - payment_price])
        invoice_line = self._receivable_lines(invoice)

        # Step 2: Reconcile each payment sequentially
        payment1_line = self._receivable_lines(payment1)
        (invoice_line | payment1_line).reconcile()
        self._assert_off_balance_lines_created(payment1, payment_price)

        payment2_line = self._receivable_lines(payment2)
        (invoice_line | payment2_line).reconcile()

        # Step 3: All payments combined cover the invoice
        self._assert_off_balance_lines_created(payment1 + payment2, amount_total)
        self.assertAlmostEqual(invoice_line.amount_residual, 0.0)

    def test_direct_multicurrency_invoice(self):
        """Test: Invoice in foreign currency with multiple lines."""
        # Step 1: Setup foreign currency (EUR)
        currency_eur = self.env.ref("base.EUR")
        currency_eur.active = True
        # Rate: 1 Company Currency = 2 EUR (so 1 EUR = 0.5 Company Currency)
        self.env["res.currency.rate"].create(
            {
                "name": fields.Date.today(),
                "rate": 2.0,
                "currency_id": currency_eur.id,
                "company_id": self.company.id,
            }
        )

        # Step 2: Create invoice in EUR
        # product_o: 1000 EUR -> 500 CC
        # product_o_2: 200 EUR -> 100 CC
        # Total: 1200 EUR -> 600 CC
        invoice = self.init_invoice(
            "out_invoice",
            post=True,
            products=[self.product_o, self.product_o_2],
            currency=currency_eur,
        )
        self.assertAlmostEqual(invoice.amount_total, 1200.0)
        self.assertAlmostEqual(invoice.amount_total_signed, 600.0)

        # Step 3: Create payment in EUR
        # We pay the full amount 1200 EUR (600 CC)
        # Receivable line: Credit 600 CC, Amount Currency -1200 EUR
        payment = self._create_payment(
            [600.0],
            currency=currency_eur,
            amounts_currency=[-1200.0],
        )

        # Step 4: Reconcile
        (self._receivable_lines(invoice) | self._receivable_lines(payment)).reconcile()

        # Step 5: Assertions
        # Check total off-balance amount in company currency (should be 600)
        off_balance_lines = self._assert_off_balance_lines_created(payment, 600.0)

        # Check amount_currency on the generated income lines
        # Should sum to -1200 EUR (Credit)
        income_lines = off_balance_lines.filtered(
            lambda line: line.account_id == self.on_balance_income_account
        )
        self.assertAlmostEqual(sum(income_lines.mapped("amount_currency")), -1200.0)
        self.assertEqual(income_lines.mapped("currency_id"), currency_eur)

        # Check individual lines distribution
        # Line 1 (product_o): 1000 EUR -> -1000 EUR amount_currency
        line_1 = income_lines.filtered(lambda line: line.product_id == self.product_o)
        self.assertEqual(len(line_1), 1)
        self.assertAlmostEqual(line_1.amount_currency, -1000.0)
        self.assertAlmostEqual(line_1.credit, 500.0)

        # Line 2 (product_o_2): 200 EUR -> -200 EUR amount_currency
        line_2 = income_lines.filtered(lambda line: line.product_id == self.product_o_2)
        self.assertEqual(len(line_2), 1)
        self.assertAlmostEqual(line_2.amount_currency, -200.0)
        self.assertAlmostEqual(line_2.credit, 100.0)

    def test_direct_multiple_payments_one_invoice_multiple_lines(self):
        """Test: Multiple payments reconciling one invoice with multiple lines.
        - Step 1: Prepare invoice with multiple lines OF THE SAME PRODUCT
          Using the same product forces aggregation of on-balance lines
          (same account/product).
        This tests that we correctly handle 'already_distributed' calculation when
        one on-balance line is linked to multiple invoice lines.
        """

        invoice = self.init_invoice(
            "out_invoice", post=True, products=[self.product_o, self.product_o]
        )
        amount_total = invoice.amount_total
        payment_amount = amount_total / 2.0

        # Step 2: Create partial payments
        payment1 = self._create_payment([payment_amount])
        payment2 = self._create_payment([payment_amount])
        invoice_line = self._receivable_lines(invoice)

        # Step 3: Reconcile first payment
        payment1_line = self._receivable_lines(payment1)
        (invoice_line | payment1_line).reconcile()

        # Assertions for first payment
        self._assert_off_balance_lines_created(payment1, payment_amount)

        # Step 4: Reconcile second payment
        payment2_line = self._receivable_lines(payment2)
        (invoice_line | payment2_line).reconcile()

        # Assertions for second payment
        self._assert_off_balance_lines_created(payment1 | payment2, payment_amount * 2)
        self.assertAlmostEqual(invoice_line.amount_residual, 0.0)

    def test_direct_one_payment_multiple_invoices(self):
        """Test: One payment paying multiple invoices (direct reconciliation)."""
        # Step 1: Prepare invoices and lump-sum payment
        invoice1 = self.init_invoice(
            "out_invoice", products=[self.product_o], post=True
        )
        invoice2 = self.init_invoice(
            "out_invoice", products=[self.product_o_2], post=True
        )
        amount_total = self.product_o.list_price + self.product_o_2.list_price
        payment = self._create_payment([amount_total])

        # Step 2: Reconcile payment with both invoices
        invoice_lines = self._receivable_lines(invoice1 + invoice2)
        payment_line = self._receivable_lines(payment)
        (invoice_lines | payment_line).reconcile()

        # Step 3: Assert line distributions (two revenues + one asset)
        self._assert_off_balance_lines_created(payment, amount_total)

    def test_direct_multiple_payments_multiple_invoices(self):
        """Test: Multiple payments reconciling multiple invoices
        with partial reconciles (direct)."""
        # Step 1: Prepare invoices
        invoice1 = self.init_invoice(
            "out_invoice", products=[self.product_o_2], post=True
        )
        invoice2 = self.init_invoice(
            "out_invoice", products=[self.product_o], post=True
        )
        invoice1_line = self._receivable_lines(invoice1)
        invoice2_line = self._receivable_lines(invoice2)

        # Step 2: First partial payment on invoice1
        partial_amount = 160.0
        payment1 = self._create_payment([partial_amount])
        payment1_line = self._receivable_lines(payment1)
        (invoice1_line | payment1_line).reconcile()
        self._assert_off_balance_lines_created(payment1, partial_amount)

        # Step 3: Second payment completes invoice1 and partially pays invoice2
        partial_amount_2 = 200.0
        payment2 = self._create_payment([partial_amount_2])
        payment2_line = self._receivable_lines(payment2)
        (payment2_line | invoice1_line).reconcile()
        (payment2_line | invoice2_line).reconcile()
        self._assert_off_balance_lines_created(
            payment1 | payment2, partial_amount + partial_amount_2
        )

        # Step 4: Unreconcile to simulate widget operations, then reconcile together
        for partial in invoice1_line.mapped("matched_credit_ids"):
            invoice1.js_remove_outstanding_partial(partial.id)
        for partial in invoice2_line.mapped("matched_credit_ids"):
            invoice2.js_remove_outstanding_partial(partial.id)
        self._assert_off_balance_lines_created(payment1 + payment2, 0.0)
        (payment1_line | payment2_line | invoice1_line | invoice2_line).reconcile()
        self._assert_off_balance_lines_created(
            payment1 + payment2, partial_amount + partial_amount_2
        )

        # Step 5: Final payment closes invoice2
        remaining_amount = (self.product_o.list_price + self.product_o_2.list_price) - (
            partial_amount + partial_amount_2
        )
        payment3 = self._create_payment([remaining_amount])
        payment3_line = self._receivable_lines(payment3)
        (invoice2_line | payment3_line).reconcile()
        self._assert_off_balance_lines_created(
            payment1 + payment2 + payment3,
            self.product_o.list_price + self.product_o_2.list_price,
        )
        self.assertAlmostEqual(invoice1_line.amount_residual, 0.0)
        self.assertAlmostEqual(invoice2_line.amount_residual, 0.0)

    # Indirect Reconciliation Tests (Direct Debit with Outstanding Account)

    def test_indirect_one_payment_one_invoice(self):
        """Test: One payment matching an existing invoice (indirect via debit order)."""
        # Step 1: Prepare indirect invoice and debit order
        invoices, debit_moves, outstanding_lines = self._prepare_indirect_invoices(
            [self.product_o]
        )
        invoice = invoices[0]
        debit_outstanding_line = outstanding_lines
        debit_outstanding_line.ensure_one()

        # Step 2: Create payment on outstanding account
        payment = self._create_payment(
            [invoice.amount_total], dst_account_id=self.outstanding_account.id
        )

        # Step 3: Reconcile payment with outstanding line
        payment_outstanding_line = self._outstanding_lines(payment)
        (debit_outstanding_line | payment_outstanding_line).reconcile()

        # Step 4: Assert off-balance outputs
        self._assert_off_balance_lines_created(payment, invoice.amount_total)
        self.assertEqual(invoice.payment_state, "paid")

    def test_indirect_one_payment_with_additional_amount(self):
        """Test: One payment with additional unreconciled amount."""
        # Step 1: Prepare indirect invoice
        invoices, debit_moves, outstanding_lines = self._prepare_indirect_invoices(
            [self.product_o]
        )
        invoice = invoices[0]
        debit_outstanding_line = outstanding_lines
        debit_outstanding_line.ensure_one()

        # Step 2: Post payment that overpays the outstanding account
        extra_amount = 150.0
        payment = self._create_payment(
            [invoice.amount_total, extra_amount],
            dst_account_id=self.outstanding_account.id,
        )
        payment_lines = self._outstanding_lines(payment)
        invoice_payment_line = payment_lines.filtered(
            lambda mvl: self.currency.is_zero(mvl.credit - invoice.amount_total)
        )
        residual_line = payment_lines - invoice_payment_line
        (debit_outstanding_line | invoice_payment_line).reconcile()

        # Step 3: Validate off-balance creation and remaining residuals
        self._assert_off_balance_lines_created(payment, invoice.amount_total)
        self.assertAlmostEqual(invoice_payment_line.amount_residual, 0.0, places=2)
        self.assertEqual(len(residual_line), 1)
        self.assertAlmostEqual(residual_line.credit, extra_amount, places=2)

    def test_indirect_multiple_payments_one_invoice(self):
        """Test: Multiple payments reconciling one invoice."""
        # Step 1: Prepare indirect invoice and outstanding line
        invoices, debit_moves, outstanding_lines = self._prepare_indirect_invoices(
            [self.product_o]
        )
        invoice = invoices[0]
        debit_outstanding_line = outstanding_lines
        debit_outstanding_line.ensure_one()
        first_amount = self.currency.round(invoice.amount_total * 0.6)
        second_amount = self.currency.round(invoice.amount_total - first_amount)

        # Step 2: First partial payment
        payment1 = self._create_payment(
            [first_amount], dst_account_id=self.outstanding_account.id
        )
        payment1_line = self._outstanding_lines(payment1)
        (debit_outstanding_line | payment1_line).reconcile()
        self._assert_off_balance_lines_created(payment1, first_amount)
        self.assertAlmostEqual(payment1_line.amount_residual, 0.0, places=2)
        self.assertAlmostEqual(
            debit_outstanding_line.amount_residual, second_amount, places=2
        )

        # Step 3: Second payment completes the invoice
        payment2 = self._create_payment(
            [second_amount], dst_account_id=self.outstanding_account.id
        )
        payment2_line = self._outstanding_lines(payment2)
        (debit_outstanding_line | payment2_line).reconcile()
        self._assert_off_balance_lines_created(
            payment1 + payment2, invoice.amount_total
        )
        self.assertAlmostEqual(payment2_line.amount_residual, 0.0, places=2)
        self.assertAlmostEqual(debit_outstanding_line.amount_residual, 0.0, places=2)

    def test_indirect_one_payment_multiple_invoices(self):
        """Test: One payment paying multiple invoices (indirect via debit order)."""
        # Step 1: Prepare indirect invoices and outstanding lines
        (
            invoices,
            debit_moves,
            debit_outstanding_lines,
        ) = self._prepare_indirect_invoices([self.product_o, self.product_o_2])

        # Step 2: Pay the sum of all invoices on the outstanding account
        payment = self._create_payment(
            invoices.mapped("amount_total"), dst_account_id=self.outstanding_account.id
        )
        payment_outstanding_lines = self._outstanding_lines(payment)
        (debit_outstanding_lines | payment_outstanding_lines).reconcile()

        # Step 3: Assert on/off balance distributions
        total_amount = sum(invoices.mapped("amount_total"))
        self._assert_off_balance_lines_created(payment, total_amount)

        # Step 4: Ensure no residuals remain
        self.assertTrue(
            all(
                self.currency.is_zero(mvl.amount_residual)
                for mvl in payment_outstanding_lines
            )
        )
        self.assertTrue(
            all(
                self.currency.is_zero(mvl.amount_residual)
                for mvl in debit_outstanding_lines
            )
        )
        self.assertSetEqual(set(invoices.mapped("payment_state")), {"paid"})

    def test_indirect_multiple_payments_multiple_invoices(self):
        """Test: Multiple payments reconciling multiple invoices
        with partial reconciles (indirect)."""
        # Step 1: Prepare invoices (sorted by amount for readability)
        invoices, debit_moves, outstanding_lines = self._prepare_indirect_invoices(
            [self.product_o_2, self.product_o]
        )
        invoices = invoices.sorted(lambda inv: inv.amount_total)
        debit_line = outstanding_lines
        total_amount = sum(invoices.mapped("amount_total"))

        # Step 2: First payment covers half of the smallest invoice
        first_payment_amount = self.currency.round(invoices[0].amount_total * 0.5)
        payment1 = self._create_payment(
            [first_payment_amount], dst_account_id=self.outstanding_account.id
        )
        payment1_line = self._outstanding_lines(payment1)
        (debit_line | payment1_line).reconcile()
        self._assert_off_balance_lines_created(payment1, first_payment_amount)
        self.assertAlmostEqual(payment1_line.amount_residual, 0.0, places=2)

        # Step 3: Second payment closes invoice1 and partially covers invoice2
        second_payment_invoice1_part = self.currency.round(
            invoices[0].amount_total - first_payment_amount
        )
        second_payment_invoice2_part = self.currency.round(
            invoices[1].amount_total * 0.4
        )
        second_payment_amount = (
            second_payment_invoice1_part + second_payment_invoice2_part
        )
        payment2 = self._create_payment(
            [second_payment_amount], dst_account_id=self.outstanding_account.id
        )
        payment2_line = self._outstanding_lines(payment2)
        (debit_line | payment2_line).reconcile()
        self._assert_off_balance_lines_created(
            payment1 + payment2, first_payment_amount + second_payment_amount
        )
        self.assertAlmostEqual(
            debit_line.amount_residual,
            total_amount - (first_payment_amount + second_payment_amount),
            places=2,
        )

        # Step 4: Final payment clears the remaining balance
        third_payment_amount = self.currency.round(
            invoices[1].amount_total - second_payment_invoice2_part
        )
        payment3 = self._create_payment(
            [third_payment_amount], dst_account_id=self.outstanding_account.id
        )
        payment3_line = self._outstanding_lines(payment3)
        (debit_line | payment3_line).reconcile()
        self._assert_off_balance_lines_created(
            payment1 + payment2 + payment3, total_amount
        )
        self.assertAlmostEqual(payment3_line.amount_residual, 0.0, places=2)
        self.assertTrue(self.currency.is_zero(debit_line.amount_residual))
        self.assertSetEqual(set(invoices.mapped("payment_state")), {"paid"})
