##############################################################################
#
#    Copyright (C) 2015-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Albert SHENOUDA <albert.shenouda@efrei.net>, Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo import fields
from odoo.tests.common import TransactionCase
import logging
import random
import string
from datetime import datetime
logger = logging.getLogger(__name__)


class BaseContractTest(TransactionCase):
    def setUp(self):
        super().setUp()
        self.thomas = self.env.ref('base.res_partner_address_3')
        self.michel = self.env.ref('base.res_partner_address_4')
        self.david = self.env.ref('base.res_partner_address_10')
        self.group_obj = self.env['recurring.contract.group'].with_context(
            async_mode=False)
        self.con_obj = self.env['recurring.contract'].with_context(
            async_mode=False)
        self.payment_mode = self.env.ref(
            'account_payment_mode.payment_mode_inbound_ct2')
        self.product = self.env.ref('product.product_product_6')
        # Make all journals cancellable
        self.env['account.journal'].search([]).write({'update_posted': True})

    def ref(self, length):
        return ''.join(random.choice(string.ascii_lowercase)
                       for i in range(length))

    def create_group(self, vals):
        base_vals = {
            'advance_billing_months': 1,
            'payment_mode_id': self.payment_mode.id,
            'change_method': 'do_nothing',
            'recurring_value': 1,
            'recurring_unit': 'month',
        }
        base_vals.update(vals)
        return self.group_obj.create(base_vals)

    def create_contract(self, vals, line_vals):
        base_vals = {
            'reference': self.ref(10),
            'next_invoice_date': fields.Date.today(),
            'state': 'draft',
            'contract_line_ids': [(0, 0, l) for l in line_vals]
        }
        for line in base_vals['contract_line_ids']:
            if 'product_id' not in line[2]:
                line[2]['product_id'] = self.product.id
            if 'quantity' not in line[2]:
                line[2]['quantity'] = 1.0
        base_vals.update(vals)
        return self.con_obj.create(base_vals)


class TestRecurringContract(BaseContractTest):
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
        # Creation of a group and a contracts with one line
        group = self.create_group({'partner_id': self.michel.id})
        contract = self.create_contract(
            {
                'partner_id': self.michel.id,
                'group_id': group.id,
            },
            [{'amount': 40.0}]
        )

        # Creation of data to test
        original_product = self.product.name
        original_partner = self.michel.name
        original_price = contract.total_amount

        # To generate invoices, the contract must be "waiting"
        contract.contract_waiting()
        self.assertEqual(contract.state, 'waiting')
        invoicer_id = contract.button_generate_invoices()
        invoices = invoicer_id.invoice_ids
        nb_invoice = len(invoices)
        # 2 invoices must be generated with our parameters
        self.assertEqual(nb_invoice, 2)
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
        group = self.create_group({'partner_id': self.michel.id})
        contract = self.create_contract(
            {
                'partner_id': self.michel.id,
                'group_id': group.id,
            },
            [{'amount': 75.0}]
        )
        contract2 = self.create_contract(
            {
                'partner_id': self.michel.id,
                'group_id': group.id,
            },
            [{'amount': 85.0}]
        )

        original_price1 = contract.total_amount
        original_price2 = contract2.total_amount

        # We put the contracts in active state to generate invoices
        contract.contract_waiting()
        contract2.contract_waiting()
        self.assertEqual(contract2.state, 'waiting')
        invoicer_obj = self.env['recurring.invoicer']
        invoicer_id = contract2.button_generate_invoices()
        invoices = invoicer_id.invoice_ids
        nb_invoice = len(invoices)
        self.assertEqual(nb_invoice, 2)
        invoice_fus = invoices[-1]
        self.assertEqual(
            original_price1 + original_price2, invoice_fus.amount_untaxed)

        # Changement of the payment option
        group.write(
            {
                'change_method': 'clean_invoices',
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
            Creation of several contracts of the same group to test the case
            if we cancel one of the contracts if invoices are still correct.
        """
        group = self.create_group({'partner_id': self.michel.id})
        contract = self.create_contract(
            {
                'partner_id': self.michel.id,
                'group_id': group.id,
            },
            [{'amount': 10.0}, {'amount': 20.0}]
        )
        contract2 = self.create_contract(
            {
                'partner_id': self.michel.id,
                'group_id': group.id,
            },
            [{'amount': 30.0}, {'amount': 40.0}]
        )
        contract3 = self.create_contract(
            {
                'partner_id': self.michel.id,
                'group_id': group.id,
            },
            [{'amount': 15.0}, {'amount': 25.0}]
        )

        # Creation of data to test
        original_product = self.product.name
        original_partner = self.michel.name
        original_price = sum((contract + contract2 + contract3).mapped(
            'total_amount'))

        # We put all the contracts in active state
        contract.contract_waiting()
        contract2.contract_waiting()
        contract3.contract_waiting()
        # Creation of a wizard to generate invoices
        invoicer = group.generate_invoices()
        invoices = invoicer.invoice_ids
        invoice = invoices[0]

        # We put the third contract in terminate state to see if
        # the invoice is well updated
        contract3.with_context(async_mode=True).action_contract_terminate()
        # Check a job for cleaning invoices has been created
        self.assertTrue(self.env['queue.job'].search([
            ('func_string', 'like', '_clean_invoices')]))
        # Force cleaning invoices immediately
        contract3._clean_invoices()
        self.assertEqual(contract3.state, 'cancelled')
        self.assertEqual(original_product, invoice.invoice_line_ids[0].name)
        self.assertEqual(original_partner, invoice.partner_id['name'])
        self.assertEqual(
            original_price - contract3.total_amount,
            invoice.amount_total)


class BaseContractCompassionTest(BaseContractTest):
    def create_contract(self, vals, line_vals):
        # Add default values
        default_values = {
            'type': 'O'
        }
        default_values.update(vals)
        return super().create_contract(default_values, line_vals)

    def _pay_invoice(self, invoice):
        bank_journal = self.env['account.journal'].search(
            [('code', '=', 'BNK1')], limit=1)
        payment = self.env['account.payment'].create({
            'journal_id': bank_journal.id,
            'amount': invoice.amount_total,
            'payment_date': invoice.date_due,
            'payment_type': 'inbound',
            'payment_method_id': bank_journal.inbound_payment_method_ids[0].id,
            'partner_type': 'customer',
            'partner_id': invoice.partner_id.id,
            'currency_id': invoice.currency_id.id,
            'invoice_ids': [(6, 0, invoice.ids)]
        })
        payment.post()


class TestContractCompassion(BaseContractCompassionTest):
    """
        Test Project contract compassion.
        We are testing 3 scenarios :
         - in the first, we are testing the changement of state of a contract
         and we are testing what is happening when we pay an invoice.
         - in the second one, we are testing what is happening when we cancel
         a contract.
         - in the last one, we are testing the _reset_open_invoices method.
    """

    def test_contract_compassion_first_scenario(self):
        """
            In this test we are testing states changement of a contract and if
            the old invoice are well cancelled when we pay one invoice.
        """
        contract_group = self.create_group({
            'advance_billing_months': 5,
            'partner_id': self.michel.id
        })
        contract = self.create_contract(
            {
                'partner_id': self.michel.id,
                'group_id': contract_group.id,
            },
            [{'amount': 40.0}]
        )
        self.assertEqual(contract.state, 'draft')

        # Switching to "waiting for payment" state
        contract.contract_waiting()
        self.assertEqual(contract.state, 'waiting')

        invoices = contract.button_generate_invoices().invoice_ids.sorted(
            'date_invoice', reverse=True)
        nb_invoices = len(invoices)
        self.assertEqual(nb_invoices, 6)
        self.assertEqual(invoices[3].state, 'open')

        # Payment of the third invoice so the
        # contract will be on the active state and the 2 first invoices should
        # be cancelled.
        self._pay_invoice(invoices[3])
        # For now the test is broken because cancel invoices are done in job.
        # TODO Would be better to launch job synchronously in the test:
        # https://github.com/OCA/queue/issues/89
        # self.assertEqual(invoices[3].state, 'paid')
        # self.assertEqual(invoices[0].state, 'open')
        # self.assertEqual(invoices[1].state, 'open')
        # self.assertEqual(invoices[2].state, 'open')
        # self.assertEqual(invoices[4].state, 'cancel')
        # self.assertEqual(invoices[5].state, 'cancel')
        self.assertEqual(contract.state, 'active')
        contract.action_contract_terminate()
        self.assertEqual(contract.state, 'terminated')

    def test_contract_compassion_second_scenario(self):
        """
            Testing if invoices are well cancelled when we cancel the related
            contract.
        """
        contract_group = self.create_group({'partner_id': self.thomas.id})
        contract = self.create_contract(
            {
                'partner_id': self.thomas.id,
                'group_id': contract_group.id,
            },
            [{'amount': 200, 'quantity': 3}])

        # Switch to "waiting for payment" state
        contract.contract_waiting()
        invoices = contract.button_generate_invoices().invoice_ids
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0].state, 'open')
        self.assertEqual(invoices[1].state, 'open')

        # Cancelling of the contract
        contract.action_contract_terminate()
        # Force cleaning invoices immediately
        contract._clean_invoices()
        self.assertEqual(contract.state, 'cancelled')
        self.assertEqual(invoices[0].state, 'cancel')
        self.assertEqual(invoices[1].state, 'cancel')

    def test_reset_open_invoices(self):
        """
            Testing of the method that update invoices when the contract
            is updated.
            THe invoice paid should not be updated, whereas the other one
            should be updated.
        """
        contract_group = self.create_group({'partner_id': self.michel.id})
        contract_group2 = self.create_group({
            'partner_id': self.david.id,
            'advance_billing_months': 2
        })
        contract = self.create_contract(
            {
                'partner_id': self.michel.id,
                'group_id': contract_group.id,
            },
            [{'amount': 60.0, 'quantity': 2}])
        contract.contract_waiting()
        invoices = contract.button_generate_invoices().invoice_ids
        self.assertEqual(len(invoices), 2)
        self._pay_invoice(invoices[1])
        # Updating of the contract
        contract.write({
            'contract_line_ids': [(1, contract.contract_line_ids.id, {
                'quantity': '3',
                'amount': '100.0',
            })]
        })
        contract.write({
            'group_id': contract_group2.id})

        # Check if the invoice unpaid is well updated
        invoice_upd = invoices[0]
        invoice_line_up = invoice_upd.invoice_line_ids[0]
        contract_line = contract.contract_line_ids
        self.assertEqual(invoice_line_up.price_unit, contract_line.amount)
        self.assertEqual(
            invoice_line_up.price_subtotal, contract_line.subtotal)

    def _test_contract_compassion_third_scenario(self):
        """
            Test the changement of a partner in a payment option and after that
            changement test if the BVR reference is set.
            Test the changement of the payment term and set it to the BVR one
            and check if the payment option of the contract has the good
            payment term.
            Test the changement of a payment option for a contract.
        """
        contract_group = self.create_group(
            'do_nothing', self.partners.ids[0], 1,
            self.payment_mode_id,
            other_vals={'recurring_value': 1, 'recurring_unit': 'month'})
        contract_group2 = self.create_group(
            'do_nothing', self.partners.ids[1], 1,
            self.payment_mode_id,
            other_vals={'recurring_value': 1, 'recurring_unit': 'month'})
        contract = self.create_contract(
            datetime.today().strftime(DF), contract_group,
            datetime.today().strftime(DF),
            other_vals={'type': 'O'})
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
