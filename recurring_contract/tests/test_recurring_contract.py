##############################################################################
#
#    Copyright (C) 2015-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Albert SHENOUDA <albert.shenouda@efrei.net>, Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################

import logging
import random
import string
from datetime import datetime, date

from odoo import fields
from odoo.tests import common
from odoo.tests.common import TransactionCase
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF

logger = logging.getLogger(__name__)


class TestRecurringContract(common.TransactionCase):
    def create_group(self, abm=1, partner_id=False, recurring_unit="month", recurring_value=1, ref="Test Group"):
        return self.env['recurring.contract.group'].create({
            'advance_billing_months': abm,
            'partner_id': partner_id or self.env.ref('base.res_partner_1').id,
            'recurring_unit': recurring_unit,
            'recurring_value': recurring_value,
            'ref': ref
        })

    def create_contract(self, reference='Test Contract', partner_id=None, group_id=None, pricelist_id=None, product_id=None, amount=10.0, quantity=1):
        return self.contract_obj.create({
            'reference': reference,
            'partner_id': partner_id or self.partner.id,
            'group_id': group_id or self.group.id,
            'pricelist_id': pricelist_id or self.env.ref('product.list0').id,
            'contract_line_ids': [
                (0, 0, {'product_id': product_id or self.product.id, 'amount': amount, 'quantity': quantity})],
        })

    def setUp(self):
        super().setUp()
        self.contract_model = self.env['recurring.contract']
        self.invoice_model = self.env['account.move']
        self.partner = self.env.ref('base.res_partner_1')
        self.partner_2 = self.env.ref('base.res_partner_2')
        self.product = self.env.ref('product.product_product_4')
        self.product_2 = self.env.ref('product.product_product_1')
        self.payment_term = self.env.ref('account.account_payment_term_immediate')
        self.journal = self.env['account.journal'].search([('company_id', '=', self.env.user.company_id.id)],
                                                          limit=1).id
        self.group = self.create_group(
            abm=1,
            partner_id=self.env.ref('base.res_partner_1').id,
            recurring_unit="month",
            recurring_value=1,
            ref="Test Group"
        )
        self.group_2 = self.create_group(
            abm=1,
            partner_id=self.env.ref('base.res_partner_2').id,
            recurring_unit="month",
            recurring_value=1,
            ref="Test Group"
        )
        self.contract_obj = self.env['recurring.contract']
        self.contract = self.create_contract(
           "Test Contract",
           self.partner.id,
           self.group.id,
           self.env.ref('product.list0').id,
           self.product.id,
           10.0,
           1,
        )
        self.contract_2 = self.create_contract(
            "Test Contract 2",
            self.partner_2.id,
            self.group.id,
            self.env.ref('product.list0').id,
            self.product.id,
            10.0,
            1,
        )
        # To generate invoices, the contract must be "waiting"
        self.contract.with_context(async_mode=False).contract_waiting()
        self.invoices = self.contract.mapped("invoice_line_ids.move_id")

    def test_build_invoice_data_contract(self):
        """
        Test building the invoice data dictionary from a recurring contract
        Asserts that the returned dictionary contains the correct invoice data and that the invoice line ids are in the
        right format
        """
        result = self.invoices[0]._build_invoices_data(contracts=self.contract)
        self.assertEqual(result.get(self.invoices[0].name).get('invoice_line_ids')[0][2],
                         {'price_unit': 10.0, 'quantity': 1})

    def test_generate_invoices(self):
        """
        Test generating invoices using the 'generate_invoices' method
        Asserts that the invoices are generated and that the async_mode context value does not affect the result
        """
        self.contract.with_context({'async_mode': False}).generate_invoices()
        # Check that invoices have been generated
        invoices = self.invoice_model.search([])
        self.assertTrue(invoices)

    def test_generate_invoices_async(self):
        """ Test the generation of invoices in async mode"""
        self.env.context = {'async_mode': True}
        self.contract.generate_invoices()
        jobs = self.env['queue.job'].search([('method_name', '=', '_generate_invoices')])
        self.assertTrue(jobs, "Async job should have been created")

    def test_get_relative_invoice_date(self):
        """
        Test the get_relative_invoice_date method
        Asserts that the method returns the correct date based on the invoice_day and the last day of the month
        """
        # Set a date to compute the invoice date for
        date_to_compute = fields.Date.from_string('2022-02-01')
        # Call the method and assert that it returns the correct date
        result = self.contract.get_relative_invoice_date(date_to_compute)
        self.assertEqual(result, fields.Date.from_string('2022-02-15'))

        # Change the invoice_day and repeat the test
        self.contract.group_id.invoice_day = '30'
        result = self.contract.get_relative_invoice_date(date_to_compute)
        self.assertEqual(result, fields.Date.from_string('2022-02-28'))

        # Check that if invoice_day is greater than the last day of the month, it is set to the last day
        date_to_compute = date(2022, 2, 28)
        result = self.contract.get_relative_invoice_date(date_to_compute)
        self.assertEqual(result, date(2022, 2, 28))


class TestRecurringContract(TestRecurringContract):
    """
        Test Project recurring contract.
        We are testing the three scenarios :
        The first one :
            - we are creating one contract
            - a payment option in which:
                - 1 invoice is generated every month
                - with 1 month of invoice generation in advance
        We are testing if invoices data are coherent with data in the
        associate contract.
        The second scenario is created to test the fusion of invoices when two
        contracts are present in same group.
        The third scenario consists in the creation of several contracts with
        several line, then we are testing that the invoices are good updated
        when we cancel one contract.
    """

    def test_generated_invoice(self):
        """
            Test the button_generate_invoices method which call a lot of
            other methods like generate_invoice(). We are testing the coherence
            of data when a contract generate invoice(s).
        """
        # Retrieving
        contract = self.contract

        # Creation of data to test
        original_product = self.product.name
        original_partner = self.partner.name
        original_price = contract.total_amount

        self.assertEqual(contract.state, 'waiting')
        invoices = contract.mapped("invoice_line_ids.move_id")
        nb_invoice = len(invoices)
        # 2 invoices must be generated with our parameters
        self.assertEqual(nb_invoice, 1)
        invoice = invoices[0]
        self.assertEqual(original_product, invoice.invoice_line_ids[0].name)
        self.assertEqual(original_partner, invoice.partner_id['name'])
        self.assertEqual(original_price, invoice.amount_untaxed)

        contract.action_contract_terminate()
        self.assertEqual(contract.state, 'cancelled')

        original_total = contract.total_amount
        self.assertEqual(original_total, invoice.amount_total)


class TestContractCompassion(TestRecurringContract):
    """
        Test Project contract compassion.
        We are testing 3 scenarios :
         - in the first, we are testing the changement of state of a contract
         and we are testing what is happening when we pay an invoice.
         - in the second one, we are testing what is happening when we cancel
         a contract.
         - in the last one, we are testing the _reset_open_invoices method.
    """

    def _pay_invoice(self, invoice):
        self.bank_journal = self.env['account.journal'].search(
            [('code', '=', 'BNK1')], limit=1)
        self.payment = self.env['account.payment'].create({
            'journal_id': self.bank_journal.id,
            'amount': invoice.amount_total,
            'date': invoice.date,
            'payment_type': 'inbound',
            'payment_method_id': self.bank_journal.inbound_payment_method_ids[0].id,
            'partner_type': 'customer',
            'partner_id': invoice.partner_id.id,
            'currency_id': invoice.currency_id.id,
            'invoice_line_ids': [(4, invoice.invoice_line_ids.ids)]
        })
        self.payment.action_post()
        invoice.payment_id = self.payment.id

    def test_contract_compassion_second_scenario(self):
        """
            Testing if invoices are well cancelled when we cancel the related
            contract.
        """
        contract = self.contract

        invoices = contract.mapped("invoice_line_ids.move_id")
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices.mapped("state"), ['posted'])

        # Cancelling of the contract
        contract.with_context(async_mode=False).action_contract_terminate()
        # Force cleaning invoices immediately
        self.assertEqual(contract.state, 'cancelled')
        self.assertEqual(invoices.mapped("state"), ['cancel'])

    def test_reset_open_invoices(self):
        """
            Testing of the method that update invoices when the contract
            is updated.
            THe invoice paid should not be updated, whereas the other one
            should be updated.
        """
        contract = self.contract
        invoices = contract.mapped("invoice_line_ids.move_id")
        self.assertEqual(len(invoices), 1)
        self._pay_invoice(invoices[0])
        # Updating of the contract
        contract.write({
            'contract_line_ids': [(1, contract.contract_line_ids.id, {
                'quantity': '3',
                'amount': '100.0',
            })]
        })
        group_2 = self.env['recurring.contract.group'].create({
            'advance_billing_months': 3,
            'partner_id': self.env.ref('base.res_partner_1').id,
            'recurring_unit': 'month',
            'recurring_value': 1,
            'ref': 'Test Group'
        })
        contract.write({'group_id': group_2.id})

        # Check if the invoice unpaid is well updated
        invoice_upd = invoices[0]
        invoice_line_up = invoice_upd.invoice_line_ids[0]
        contract_line = contract.contract_line_ids
        self.assertEqual(invoice_line_up.price_unit, contract_line.amount)
        self.assertEqual(invoice_line_up.price_subtotal, contract_line.subtotal)

    def _test_contract_compassion_third_scenario(self):
        """
            Test the changement of a partner in a payment option and after that
            changement test if the BVR reference is set.
            Test the changement of the payment term and set it to the BVR one
            and check if the payment option of the contract has the good
            payment term.
            Test the changement of a payment option for a contract.
        """
        contract_group = self.group
        contract_group2 = self.env['recurring.contract.group'].create({
            'advance_billing_months': 3,
            'partner_id': self.env.ref('base.res_partner_1').id,
            'recurring_unit': 'month',
            'recurring_value': 1,
            'ref': 'Test Group'
        })
        contract = self.contract
        contract_group.write({'partner_id': self.partners.ids[1]})
        contract_group.on_change_partner_id()
        self.assertTrue(contract_group.bvr_reference)
        payment_mode_2 = self.env.ref(
            'account_payment_mode.payment_mode_inbound_dd1')
        contract_group2.write({'payment_mode_id': payment_mode_2.id})
        contract_group2.on_change_payment_mode()
        self.assertTrue(contract_group2.bvr_reference)
        contract.contract_waiting()
        contract.write({'group_id': contract_group2.id})
        contract.on_change_group_id()
        self.assertEqual(
            contract.group_id.payment_mode_id, payment_mode_2)

    def test_change_contract_group(self):
        """
            Test correct behavior on contract_group change.
            when change method is set to clean invoices changing the advance billing
            month should regenerate the invoices for this contract.
        """
        contract_group = self.group
        contract = self.contract
        total_amount = contract.total_amount

        invoices = contract.mapped("invoice_line_ids.move_id")
        self.assertEqual(len(invoices), 1)

        contract_group.with_context(async_mode=False).write(
            {"advance_billing_months": 3})

        self.assertEqual(len(contract.invoice_line_ids.mapped("move_id")), 3)
        for inv in contract.invoice_line_ids.mapped("move_id"):
            self.assertEqual(total_amount, inv.amount_untaxed)

    def _test_invoice_generation_behavior_on_new_contract_in_group(self):
        """When a new contract is added to a contract group invoices should be merged"""

        contract_group = self.group
        contract = self.contract
        contract.contract_waiting()
        invoices = contract.button_generate_invoices().invoice_ids

        self.assertEqual(len(invoices), 2)

        self._pay_invoice(invoices[-1])

        self.assertEqual(invoices[-1].state, "paid")

        contract2 = self.contract_2
        contract2.contract_waiting()
        contract2.button_generate_invoices()

        self.assertEqual(len(contract_group.mapped("contract_ids.invoice_line_ids.invoice_id")), 3)
