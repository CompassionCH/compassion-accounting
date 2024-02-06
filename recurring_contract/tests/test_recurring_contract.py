##############################################################################
#
#    Copyright (C) 2015-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Albert SHENOUDA <albert.shenouda@efrei.net>, Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from dateutil.relativedelta import relativedelta
from dateutil.utils import today
from odoo.tests.common import TransactionCase
import logging
import random
import string

logger = logging.getLogger(__name__)


def test_generate_invoice(contract):
    contract.ensure_one()
    contract.generate_invoices()
    return contract.invoice_line_ids.mapped("move_id")


class BaseContractTest(TransactionCase):
    """Basic class that gives access to helper to generate some test"""

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].set_param(f'recurring_contract.do_generate_curr_month_{self.env.company.id}', 'False')
        self.env['ir.config_parameter'].set_param(f'recurring_contract.inv_block_day_{self.env.company.id}', 31)
        self.partner_1 = self.env.ref('base.res_partner_address_1')
        self.partner_2 = self.env.ref('base.res_partner_address_2')
        self.partner_3 = self.env.ref('base.res_partner_address_3')
        self.RecurringContractGroup = self.env['recurring.contract.group'].with_context(
            async_mode=False)
        self.RecurringContract = self.env['recurring.contract'].with_context(
            async_mode=False)
        self.payment_mode = self.env.ref('account_payment_mode.payment_mode_inbound_ct2')
        self.product = self.env.ref('product.product_product_1')
        self.product_2 = self.env.ref('product.product_product_2')
        # Creation of a group and a contracts with one line
        self.group = self.create_group({'partner_id': self.partner_1.id})
        self.contract = self.create_contract(
            {
                'partner_id': self.partner_1.id,
                'group_id': self.group.id,
            },
            [{'amount': 40.0, 'product_id': self.product.id}]
        )

    def ref(self, length):
        return ''.join(random.choice(string.ascii_lowercase)
                       for i in range(length))

    def create_group(self, vals):
        base_vals = {
            'advance_billing_months': 1,
            'payment_mode_id': self.payment_mode.id,
            'recurring_value': 1,
            'recurring_unit': 'month',
        }
        base_vals.update(vals)
        return self.RecurringContractGroup.create(base_vals)

    def create_contract(self, vals, line_vals):
        name = self.ref(10)
        base_vals = {
            'reference': name,
            'state': 'draft',
            'pricelist_id': self.env['product.pricelist'].create({
                "name": "global pricelist",
                "company_id": self.env.ref("base.main_company").id,
                "item_ids": [
                    (
                        0,
                        0,
                        {
                            "product_tmpl_id": False,
                            "base": "list_price",
                            "fixed_price": 10,
                            "applied_on": "3_global",
                        },
                    )
                ],
            }).id,
            'contract_line_ids': [(0, 0, l) for l in line_vals]
        }
        for line in base_vals['contract_line_ids']:
            if 'product_id' not in line[2]:
                line[2]['product_id'] = self.product.id
            if 'quantity' not in line[2]:
                line[2]['quantity'] = 1.0
        base_vals.update(vals)
        return self.RecurringContract.create(base_vals)

    def _pay_invoices(self, invoices):
        for invoice in invoices:
            self._pay_invoice(invoice)

    def _pay_invoice(self, invoice):
        invoice.ensure_one()
        bank_journal = self.env["account.journal"].search(
            [("code", "=", "BNK1")], limit=1
        )
        # Generate payment with the wizard (the context simulate what's done in the web interface)
        self.env["account.payment.register"].with_context({
            "active_ids": invoice.ids,
            "active_model": invoice._name
        }).create(
            {
                "journal_id": bank_journal.id,
                "amount": invoice.amount_total,
                "payment_date": invoice.invoice_date_due,
                "payment_method_id": bank_journal.inbound_payment_method_ids[0].id,
                "partner_type": "customer",
            }
        ).action_create_payments()


class TestRecurringContract(BaseContractTest):
    """
        Test Project recurring contract.
    """

    def test_contract_basic_workflow(self):
        """
            Test the basic workflow of a contract.
            Created in draft -> Waiting with invoices generated -> active by paying the invoices
            -> terminated
        """
        contract = self.contract
        # We validate the contract
        # When the contract is in waiting state it should generate invoices
        contract.contract_waiting()
        self.assertEqual(contract.state, 'waiting')
        invoices = contract.invoice_line_ids.mapped("move_id")
        # Ensure the good number of moves are generated 2 (for current month and next month)
        self.assertEqual(len(invoices), 1)
        # Ensure once the invoice has been paid the contract is active
        self._pay_invoices(invoices)
        self.assertEqual(contract.state, 'active')
        # We end a contract it should put it in state terminated if it has been activated
        contract.action_contract_terminate()
        self.assertEqual(contract.state, 'terminated')
        # Ensure the cancellation of all invoices
        invoices = contract.invoice_line_ids.mapped("move_id").filtered(
            lambda m: m.state == "posted"
                      and m.payment_state == "not_paid"
        )
        self.assertEqual(len(invoices), 0)

    def test_infinite_invoice_gen(self):
        """We try to see if the invoices would infinitely generate"""
        contract = self.contract
        self.assertEqual(len(contract.contract_line_ids), 1)
        contract.contract_waiting()
        # We try to generate thousand times the same contract
        for i in range(0, 10):
            contract.button_generate_invoices()
        invoices = contract.invoice_line_ids.mapped("move_id")
        # Ensure that the number of invoices didn't exploded
        self.assertEqual(len(invoices), 1)

    def test_invoice_suspension(self):
        """We test the field invoice suspension"""
        contract = self.contract
        # don't generate the two first s invoices
        contract.group_id.write({
            'invoice_suspended_until': (today() + relativedelta(months=1)).date(),
        })
        self.assertEqual(len(contract.contract_line_ids), 1)
        contract.contract_waiting()
        contract.button_generate_invoices()
        invoices = contract.invoice_line_ids.mapped("move_id")
        # Ensure that no invoices has been generated
        self.assertEqual(len(invoices), 0)

    def test_generate_invoice_data_coherency(self):
        """
            We test the generations and coherence of the invoices generated
            We also test to modfiy the contract it should update the invoice
        """
        contract = self.contract
        self.assertEqual(len(contract.contract_line_ids), 1)
        # We validate the contract
        # When the contract is in waiting state it should generate invoices
        contract.contract_waiting()
        invoices = contract.invoice_line_ids.mapped("move_id")
        # Ensure the good number of moves are generated 2 (for current month and next month)
        self.assertEqual(len(invoices), 1)
        # Ensure that the data of the invoice are correct
        for invoice in invoices:
            self.assertEqual(invoice.partner_id, contract.partner_id, "The partners doesn't match")
            self.assertEqual(invoice.payment_mode_id, contract.group_id.payment_mode_id)
            for invoice_line in invoice.invoice_line_ids:
                self.assertEqual(invoice_line.contract_id, contract)
                self.assertEqual(invoice_line.product_id, contract.contract_line_ids[0].product_id)
                self.assertEqual(invoice_line.quantity, contract.contract_line_ids[0].quantity)
                self.assertEqual(invoice_line.price_unit, contract.contract_line_ids[0].amount)
        contract.write({
            "partner_id": self.partner_2.id,
            "group_id": self.create_group({"partner_id": self.partner_2.id})
        })
        self.assertEqual(invoices.mapped("partner_id"), contract.partner_id)
        contract.group_id.write({
            "advance_billing_months": 3
        })
        invoices = contract.invoice_line_ids.mapped("move_id")
        self.assertEqual(len(invoices), 3)

    def test_invoice_multiple_contract_one_pay_opt(self):
        """
            We want to test the behaviour of the generation of invoices
            when we have multiple contract on one payment option
            It should generate one invoice with multiple invoice line
        """
        contract = self.contract
        self.assertEqual(len(contract.contract_line_ids), 1)
        contract_2 = self.create_contract(
            {
                'partner_id': contract.partner_id.id,
                'group_id': contract.group_id.id,
            },
            [{'amount': 20.0, 'product_id': self.product_2.id}]
        )
        contracts = contract + contract_2
        # We validate the contract
        # When the contract is in waiting state it should generate invoices
        contracts.contract_waiting()
        invoices = contracts.mapped("invoice_line_ids.move_id")
        # Ensure the good number of moves are generated 2 (for current month and next month)
        self.assertEqual(len(invoices), 1)
        # Ensure that the data of the invoice are correct
        contract_lines = contracts.mapped("contract_line_ids")
        for invoice in invoices:
            self.assertEqual(invoice.partner_id, contract.partner_id, "The partners doesn't match")
            self.assertEqual(invoice.payment_mode_id, contract.group_id.payment_mode_id)
            invoice_lines = invoice.invoice_line_ids
            self.assertListEqual(invoice_lines.mapped("contract_id").ids, contracts.ids)
            self.assertListEqual(invoice_lines.mapped("product_id").ids, contract_lines.mapped("product_id").ids)
            self.assertListEqual(invoice_lines.mapped("quantity"), contract_lines.mapped("quantity"))
            self.assertListEqual(invoice_lines.mapped("price_unit"), contract_lines.mapped("amount"))
        # Terminating one contract (line should be erased of the open invoice
        contracts[0].action_contract_terminate()
        no_invoice = invoices.mapped("invoice_line_ids").filtered(lambda l: l.contract_id == contracts[0])
        self.assertEqual(len(no_invoice), 0)

    def test_invoice_create_contract_invoice_already_paid(self):
        """
            We are testing that when creating a new contract on existing payment option
            that has some invoices already paid.
            A new invoice is generated for the contract just created.
        """
        contract = self.contract
        self.assertEqual(len(contract.contract_line_ids), 1)
        contract_2 = self.create_contract(
            {
                'partner_id': contract.partner_id.id,
                'group_id': contract.group_id.id,
            },
            [{'amount': 20.0, 'product_id': self.product_2.id}]
        )
        contract.contract_waiting()
        invoices = contract.mapped("invoice_line_ids.move_id")
        self.assertEqual(len(invoices), 1)
        self.assertEqual(len(invoices.mapped("invoice_line_ids")), 1)
        self._pay_invoices(invoices)
        contract_2.contract_waiting()
        contract_2.button_generate_invoices()
        contracts = contract + contract_2
        invoices_after = contracts.mapped("invoice_line_ids.move_id")
        self.assertEqual(len(invoices_after), 2)
        self.assertListEqual(invoices_after.mapped("amount_total"), contracts.mapped("total_amount"))

    def test_invoice_create_contract_invoice_already_paid_do_gen_curr_month(self):
        """
            We are testing that when creating a new contract on existing payment option
            that has some invoices already paid.
            A new invoice is generated for the contract just created.
        """
        self.env['ir.config_parameter'].set_param(f'recurring_contract.do_generate_curr_month_{self.env.company.id}', 'True')
        contract = self.contract
        self.assertEqual(len(contract.contract_line_ids), 1)
        contract_2 = self.create_contract(
            {
                'partner_id': contract.partner_id.id,
                'group_id': contract.group_id.id,
            },
            [{'amount': 20.0, 'product_id': self.product_2.id}]
        )
        contract.contract_waiting()
        invoices = contract.mapped("invoice_line_ids.move_id")
        self.assertEqual(len(invoices), 2)
        self.assertEqual(len(invoices.mapped("invoice_line_ids")), 2)
        self._pay_invoices(invoices)
        contract_2.contract_waiting()
        contract_2.button_generate_invoices()
        contracts = contract + contract_2
        invoices_after = contracts.mapped("invoice_line_ids.move_id")
        self.assertEqual(len(invoices_after), 4)
        amounts = contracts.mapped("total_amount")*2
        amounts.sort(reverse=True)
        self.assertEqual(invoices_after.mapped("amount_total"), amounts)
