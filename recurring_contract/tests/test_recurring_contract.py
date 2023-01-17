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
    def setUp(self):
        super().setUp()
        self.contract_model = self.env['recurring.contract']
        self.invoice_model = self.env['account.move']
        self.partner = self.env.ref('base.res_partner_1')
        self.product = self.env.ref('product.product_product_4')
        self.product_2 = self.env.ref('product.product_product_1')
        self.payment_term = self.env.ref('account.account_payment_term_immediate')
        self.journal = self.env['account.journal'].search([('company_id', '=', self.env.user.company_id.id)],
                                                          limit=1).id
        self.group = self.env['recurring.contract.group'].create({
            'advance_billing_months': 1,
            'partner_id': self.env.ref('base.res_partner_1').id,
            'recurring_unit': 'month',
            'recurring_value': 1,
            'ref': 'Test Group'
        })
        # Create a new contract with a set invoice_day
        self.contract_obj = self.env['recurring.contract']
        self.contract = self.contract_obj.create({
            'reference': 'Test Contract',
            'partner_id': self.partner.id,
            'group_id': self.group.id,
            'pricelist_id': self.env.ref('product.list0').id,
            'contract_line_ids': [(0, 0, {'product_id': self.product.id, 'amount': 10.0, 'quantity': 1})],
            'invoice_day': '15',
        })
        self.contract_2 = self.contract_obj.create({
            'reference': 'Test Contract 2',
            'partner_id': self.partner.id,
            'group_id': self.group.id,
            'pricelist_id': self.env.ref('product.list0').id,
            'contract_line_ids': [(0, 0, {'product_id': self.product.id, 'amount': 30.0, 'quantity': 1}),
                                  (0, 0, {'product_id': self.product_2.id, 'amount': 40.0, 'quantity': 1})],
            'invoice_day': '15',
        })
        self.contract_3 = self.contract_obj.create({
            'reference': 'Test Contract 3',
            'partner_id': self.partner.id,
            'group_id': self.group.id,
            'pricelist_id': self.env.ref('product.list0').id,
            'contract_line_ids': [(0, 0, {'product_id': self.product.id, 'amount': 15.0, 'quantity': 1}),
                                  (0, 0, {'product_id': self.product_2.id, 'amount': 25.0, 'quantity': 1})],
            'invoice_day': '15',
        })
        # To generate invoices, the contract must be "waiting"
        self.contract.with_context(async_mode=False).contract_waiting()
        self.invoices = self.contract.mapped("invoice_line_ids.move_id")

    def test_build_invoice_data_contract(self):
        """
        Test building the invoice data dictionary from a recurring contract
        Asserts that the returned dictionary contains the correct invoice data and that the invoice line ids are in the
        right format
        """
        result = self.invoices[0]._build_invoice_data(contract=self.contract)
        self.assertEqual(result.get(self.invoices[0].name).get('invoice_line_ids')[0][2], {'price_unit': 10.0, 'quantity': 1})

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
        self.contract.invoice_day = '30'
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
        invoice = invoices[1]
        self.assertEqual(original_product, invoice.invoice_line_ids[0].name)
        self.assertEqual(original_partner, invoice.partner_id['name'])
        self.assertEqual(original_price, invoice.amount_untaxed)

        contract.action_contract_terminate()
        self.assertEqual(contract.state, 'cancelled')

        original_total = contract.total_amount
        self.assertEqual(original_total, invoice.amount_total)

    def test_generated_invoice_second_scenario(self):
        """
            Creation of the second contract to test the fusion of invoices if
            the partner and the dates are the same. Then there is the test of
            the changement of the payment option and its consequences : check
            if all data of invoices generated are correct, and if the number
            of invoices generated is correct
        """
        # Creation of a group and two contracts with one line each
        group = self.group
        contract = self.contract
        contract2 = self.contract_2

        original_price1 = contract.total_amount
        original_price2 = contract2.total_amount

        contract2.with_context(async_mode=False).contract_waiting()
        self.assertEqual(contract2.state, 'waiting')
        invoicer_obj = self.env['recurring.invoicer']
        invoices = contract.mapped("invoice_line_ids.move_id") + contract2.mapped("invoice_line_ids.move_id")
        nb_invoice = len(invoices)
        self.assertEqual(nb_invoice, 4)
        invoice_fus = invoices[-1]
        self.assertEqual(original_price1 + original_price2, invoice_fus.amount_untaxed)

        # Changement of the payment option
        group.write(
            {
                'recurring_value': 2,
                'recurring_unit': 'week',
                'advance_billing_months': 2,
            })
        new_invoicer_id = invoicer_obj.search([], limit=1)
        new_invoices = new_invoicer_id.invoice_ids
        nb_new_invoices = len(new_invoices)
        self.assertEqual(nb_new_invoices, 5)

        # Copy of one contract to test copy method()
        contract_copied = contract2.copy()
        self.assertTrue(contract_copied.id)
        contract_copied.contract_waiting()
        self.assertEqual(contract_copied.state, 'waiting')
        contract_copied_line = contract_copied.contract_line_ids[0]
        contract_copied_line.write({'amount': 160.0})
        new_price2 = contract_copied_line.subtotal
        invoicer_id = self.env[
            'recurring.invoicer.wizard'].with_context(
            async_mode=False).generate().get('res_id')
        invoicer_wiz = self.env['recurring.invoicer'].browse(invoicer_id)
        new_invoices = invoicer_wiz.invoice_ids
        new_invoice_fus = new_invoices.filtered(
            lambda i: i.mapped(
                'invoice_line_ids.contract_id') == contract_copied
        )[0]
        self.assertEqual(new_price2, new_invoice_fus.amount_total)

    def test_generated_invoice_third_scenario(self):
        """
        It creates a group of contracts, then it creates 3 contracts in the group.
        Then it creates a wizard to generate invoices. Then it cancels the third contract.
        Then it checks if the invoice is well updated.
        """
        contract = self.contract
        contract2 = self.contract_2
        contract3 = self.contract_3

        # Creation of data to test
        original_product = self.product.name
        original_partner = self.partner.name

        # We put all the contracts in active state
        contract.with_context(async_mode=False).contract_waiting()
        contract2.with_context(async_mode=False).contract_waiting()
        contract3.with_context(async_mode=False).contract_waiting()
        # Creation of a wizard to generate invoices
        invoice = contract3.invoice_line_ids.mapped("move_id")

        # We put the third contract in terminate state to see if
        # the invoice is well updated
        contract3.with_context(async_mode=True).action_contract_terminate()
        # Check a job for cleaning invoices has been created
        self.assertTrue(self.env['queue.job'].search([]))
        # Force cleaning invoices immediately
        self.assertEqual(contract3.state, 'cancelled')
        self.assertEqual(original_product, invoice.invoice_line_ids[0].name)
        self.assertEqual(original_partner, invoice.partner_id['name'])
        self.assertEqual(contract3.total_amount, invoice.amount_total)
        self.assertEqual("cancel", invoice.state)


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
            'invoice_line_ids': [(6, 0, invoice.invoice_line_ids.ids)]
        })

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
        contract.action_contract_terminate()
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
        self.assertEqual(len(invoices), 2)
        self._pay_invoice(invoices[1])
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

    def test_keep_paid_invoice_on_group_change(self):
        contract_group = self.group
        contract = self.contract

        invoices = contract.mapped("invoice_line_ids.move_id")
        self.assertEqual(len(invoices), 1)

        # ensure we pay the most earliest invoice
        invoice_to_pay = self.env["account.move"].search([
            ("id", "in", invoices.ids)], order="invoice_date asc", limit=1)
        self._pay_invoice(invoice_to_pay)
        self.assertEqual(invoice_to_pay.payment_state, "paid")

        # changing advance billing to one month
        # 2 month are now obsolete but one is paid
        # so 1 invoice cancel and 1 invoice paid
        contract_group.with_context(async_mode=False).write({
            "advance_billing_months": 1
        })

        invoices = contract.invoice_line_ids.mapped("invoice_id")

        # number of invoices should remain the same
        self.assertEqual(len(invoices), 4)

        # 1 invoice should still be paid
        self.assertEqual(len(invoices.filtered(lambda x: x.state == "paid")), 1)

        # 2 invoices should be open
        self.assertEqual(len(invoices.filtered(lambda x: x.state == "open")), 1)

        # 1 invoice should be canceled
        self.assertEqual(len(invoices.filtered(lambda x: x.state == "cancel")), 2)

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

        self.assertEqual(
            len(contract_group.mapped("contract_ids.invoice_line_ids.invoice_id")), 3)

    def test_multiple_paid_in_clean_range(self):
        """assess good behavior if we found multiple paid invoices in
        the month to come and we do a clean"""

        contract_group = self.group
        contract = self.contract
        contract.with_context(async_mode=False).contract_waiting()
        invoices = contract.mapped("invoice_line_ids.move_id")

        sorted_invoices = sorted(invoices, key=lambda e: e.date)

        self.assertEqual(len(sorted_invoices), 1)

        for inv in sorted_invoices[:3]:
            self._pay_invoice(inv)
            self.assertEqual(inv.payment_state, "paid")

        contract_group.cancel_contract_invoices()

        all_contract_invoice = self.env["account.move.line"].search([
            ("contract_id", "=", contract.id)]).mapped("invoice_id")

        self.assertEqual(len(all_contract_invoice), 4)
