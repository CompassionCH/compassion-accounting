# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Albert SHENOUDA <albert.shenouda@efrei.net>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from datetime import datetime, timedelta
from openerp import netsvc
from openerp.addons.recurring_contract.tests.test_base_contract \
    import test_base_contract
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF
import logging
logger = logging.getLogger(__name__)


class test_recurring_contract(test_base_contract):
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
        contract.
        The third scenario consists in the creation of several contracts with
        several line, then we are testing that the invoices are good updated
        when we cancel one contract.
    """

    def setUp(self):
        super(test_recurring_contract, self).setUp()

    def test_generated_invoice(self):
        """
            Test the button_generate_invoices method which call a lot of
            other methods like generate_invoice(). We are testing the coherence
            of data when a contract generate invoice(s).
        """
        # Creation of a group and a contracts with one line
        group = self._create_group(
            'do_nothing', self.partners.ids[0], 1, self.payment_term_id,
            other_vals={'recurring_value': 1, 'recurring_unit': 'month'})
        contract = self._create_contract(
            datetime.today().strftime(DF), group,
            datetime.today().strftime(DF))
        contract_line = self._create_contract_line(
            contract.id, '40.0')

        # Creation of data to test
        original_product = contract_line.product_id['name']
        original_partner = contract.partner_id['name']
        original_price = contract_line.subtotal
        original_start_date = contract.start_date

        # To generate invoices, the contract must be "active"
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(self.uid, 'recurring.contract',
                                contract.id, 'contract_validated',
                                self.cr)
        self.assertEqual(contract.state, 'active')
        invoicer_id = contract.button_generate_invoices()
        invoices = invoicer_id.invoice_ids
        nb_invoice = len(invoices)
        # 2 invoices must be generated with our parameters
        self.assertEqual(nb_invoice, 2)
        invoice = invoices[0]
        self.assertEqual(original_product, invoice.invoice_line[0].name)
        self.assertEqual(original_partner, invoice.partner_id['name'])
        self.assertEqual(original_price, invoice.amount_untaxed)
        self.assertEqual(original_start_date, invoice.date_invoice)

        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(self.uid, 'recurring.contract',
                                contract.id, 'contract_terminated',
                                self.cr)
        self.assertEqual(contract.state, 'terminated')

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
        group = self._create_group(
            'do_nothing', self.partners.ids[1], 2,
            self.payment_term_id, '137 option payement',
            other_vals={'recurring_value': 1, 'recurring_unit': 'month'})

        contract = self._create_contract(
            datetime.today() + timedelta(days=2), group,
            datetime.today() + timedelta(days=2))
        contract_line = self._create_contract_line(contract.id, '75.0')
        contract2 = self._create_contract(
            datetime.today() + timedelta(days=2),
            group, datetime.today() + timedelta(days=2))
        contract_line2 = self._create_contract_line(
            contract2.id, '85.0')

        original_price1 = contract_line.subtotal
        original_price2 = contract_line2.subtotal

        # We put the contracts in active state to generate invoices
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            contract.id, 'contract_validated', self.cr)
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            contract2.id, 'contract_validated', self.cr)
        self.assertEqual(contract2.state, 'active')
        invoicer_obj = self.env['recurring.invoicer']
        invoicer_id = contract2.button_generate_invoices()
        invoices = invoicer_id.invoice_ids
        nb_invoice = len(invoices)
        self.assertEqual(nb_invoice, 2)
        invoice_fus = invoices[0]
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
        new_invoicer_id = invoicer_obj.search([], order='id DESC')[0]
        new_invoices = new_invoicer_id.invoice_ids
        nb_new_invoices = len(new_invoices)
        self.assertEqual(nb_new_invoices, 5)

        # Copy of one contract to test copy method()
        contract2.copy()
        contract_copied = self.env['recurring.contract'].search([
            ('state', '=', 'draft'),
            ('partner_id', '=', self.partners.ids[1])], order='id DESC')[0]
        self.assertTrue(contract_copied.id)
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            contract_copied.id, 'contract_validated', self.cr)
        self.assertEqual(contract_copied.state, 'active')
        contract_copied_line = contract_copied.contract_line_ids[0]
        contract_copied_line.write({'amount': 160.0})
        new_price2 = contract_copied_line.subtotal
        invoicer_wizard_obj = self.env['recurring.invoicer.wizard']
        invoicer_wiz_id = invoicer_wizard_obj.generate()
        invoicer_wiz = self.env['recurring.invoicer'].browse(
            invoicer_wiz_id['res_id'])
        new_invoices = invoicer_wiz.invoice_ids
        new_invoice_fus = new_invoices[0]
        self.assertEqual(new_price2, new_invoice_fus.amount_untaxed)

    def test_generated_invoice_third_scenario(self):
        """
            Creation of several contracts of the same group to test the case
            if we cancel one of the contracts if invoices are still correct.
        """
        # Creation of a group
        group = self._create_group(
            'do_nothing', self.partners.ids[0], 1,
            self.payment_term_id,
            other_vals={'recurring_value': 1, 'recurring_unit': 'month'})

        # Creation of three contracts with two lines each
        contract = self._create_contract(
            datetime.today().strftime(DF), group,
            datetime.today().strftime(DF))
        contract2 = self._create_contract(
            datetime.today().strftime(DF), group,
            datetime.today().strftime(DF))
        contract3 = self._create_contract(
            datetime.today().strftime(DF), group,
            datetime.today().strftime(DF))

        contract_line0 = self._create_contract_line(
            contract.id, '10.0')
        contract_line1 = self._create_contract_line(
            contract.id, '20.0')
        contract_line2 = self._create_contract_line(
            contract2.id, '30.0')
        contract_line3 = self._create_contract_line(
            contract2.id, '40.0')
        contract_line4 = self._create_contract_line(
            contract3.id, '15.0')
        contract_line5 = self._create_contract_line(
            contract3.id, '25.0')

        # Creation of data to test
        original_product = contract_line0.product_id['name']
        original_partner = contract.partner_id['name']
        original_price = sum([contract_line0.subtotal,
                              contract_line1.subtotal,
                              contract_line2.subtotal,
                              contract_line3.subtotal,
                              contract_line4.subtotal,
                              contract_line5.subtotal])
        original_start_date = contract.start_date

        # We put all the contracts in active state
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            contract.id, 'contract_validated', self.cr)
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            contract2.id, 'contract_validated', self.cr)
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            contract3.id, 'contract_validated', self.cr)

        # Creation of a wizard to generate invoices
        invoicer_id = self.env['recurring.invoicer.wizard'].generate()
        invoicer = self.env['recurring.invoicer'].browse(invoicer_id['res_id'])
        invoices = invoicer.invoice_ids
        invoice = invoices[0]
        invoice2 = invoices[1]

        # We put the third contract in terminate state to see if
        # the invoice is well updated
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            contract3.id, 'contract_terminated', self.cr)
        self.assertEqual(contract3.state, 'terminated')
        self.assertEqual(original_product, invoice.invoice_line[0].name)
        self.assertEqual(original_partner, invoice.partner_id['name'])
        self.assertEqual(
            original_price - contract3.total_amount,
            invoice.amount_untaxed)
        self.assertEqual(original_start_date, invoice2.date_invoice)
