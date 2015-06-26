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

from openerp.tests import common
from datetime import datetime, timedelta
from openerp import netsvc
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF
import logging
logger = logging.getLogger(__name__)


class test_recurring_contract(common.TransactionCase):
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
        # Creation of an account
        account_type = self.registry('account.account.type').search(
            self.cr, self.uid, [
                ('close_method', '=', 'unreconciled'),
            ])[0]
        property_account_receivable = self.registry('account.account').search(
            self.cr, self.uid, [
                ('type', '=', 'receivable'),
                ('user_type', '=', account_type)
            ])[0]
        property_account_payable = self.registry('account.account').search(
            self.cr, self.uid, [('type', '=', 'payable')])[0]

        # Creation of partners
        partner_obj = self.registry('res.partner')
        self.partner_id = partner_obj.create(self.cr, self.uid, {
            'name': 'Monsieur Client 137',
            'property_account_receivable': property_account_receivable,
            'property_account_payable': property_account_payable,
        })
        self.partner_id1 = partner_obj.create(self.cr, self.uid, {
            'name': 'Client 137',
            'property_account_receivable': property_account_receivable,
            'property_account_payable': property_account_payable,
        })
        # Creation of payement terms
        payment_term_obj = self.registry('account.payment.term')
        self.payment_term_id = payment_term_obj.search(self.cr, self.uid, [
            ('name', '=', '15 Days')
        ])[0]

    def _create_contract(self, start_date, group_id, next_invoice_date):
        """
            Create a contract. For that purpose we have created a partner
            to get his id
        """
        # Creation of a contract
        contract_obj = self.registry('recurring.contract')
        group_obj = self.registry('recurring.contract.group')
        group = group_obj.browse(self.cr, self.uid, group_id)
        partner_id = group.partner_id.id
        contract_id = contract_obj.create(self.cr, self.uid, {
            'start_date': start_date,
            'partner_id': partner_id,
            'group_id': group_id,
            'next_invoice_date': next_invoice_date,
        })
        return contract_id

    def _create_contract_line(self, contract_id, price):
        """ Create contract's lines """
        contract_line_obj = self.registry('recurring.contract.line')
        contract_line_id = contract_line_obj.create(self.cr, self.uid, {
            'product_id': 1,
            'amount': price,
            'contract_id': contract_id,
        })
        return contract_line_id

    def _create_group(self, change_method, rec_value, rec_unit, partner_id,
                      adv_biling_months, payment_term_id, ref=None):
        """
            Create a group with 2 possibilities :
                - ref is not given so it takes "/" default values
                - ref is given
        """
        group_obj = self.registry('recurring.contract.group')
        group_id = group_obj.create(self.cr, self.uid, {
            'partner_id': partner_id,
        })
        group = group_obj.browse(self.cr, self.uid, group_id)
        group_vals = {
            'change_method': change_method,
            'recurring_value': rec_value,
            'recurring_unit': rec_unit,
            'partner_id': partner_id,
            'advance_billing_months': adv_biling_months,
            'payment_term_id': payment_term_id,
        }
        if ref:
            group_vals['ref'] = ref
        group.write(group_vals)
        return group_id

    def test_generated_invoice(self):
        """
            Test the button_generate_invoices method which call a lot of
            other methods like generate_invoice(). We are testing the coherence
            of data when a contract generate invoice(s).
        """
        # Creation of a group and a contracts with one line
        self.contract_group = self._create_group(
            'do_nothing', 1, 'month', self.partner_id, 1, self.payment_term_id)
        self.contract_id = self._create_contract(
            datetime.today().strftime(DF), self.contract_group,
            datetime.today().strftime(DF))
        self.contract_line_id = self._create_contract_line(
            self.contract_id, '40.0')
        contract = self.registry('recurring.contract')
        contract_obj = contract.browse(self.cr, self.uid, self.contract_id)
        contract_line = self.registry('recurring.contract.line')
        contract_line_obj = contract_line.browse(self.cr, self.uid,
                                                 self.contract_line_id)

        # Creation of data to test
        original_product = contract_line_obj.product_id['name']
        original_partner = contract_obj.partner_id['name']
        original_price = contract_line_obj.subtotal
        original_start_date = contract_obj.start_date

        # To generate invoices, the contract must be "active"
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(self.uid, 'recurring.contract',
                                self.contract_id, 'contract_validated',
                                self.cr)
        contract_act = contract.browse(self.cr, self.uid, self.contract_id)
        self.assertEqual(contract_act.state, 'active')
        invoicer = self.registry('recurring.invoicer')
        invoicer_id = contract_act.button_generate_invoices()
        invoicer_obj = invoicer.browse(self.cr, self.uid, invoicer_id)
        invoices = invoicer_obj.invoice_ids
        nb_invoice = len(invoices)
        # 2 invoices must be generated with our parameters
        self.assertEqual(nb_invoice, 2)
        invoice = invoices[0]
        invoice2 = invoices[1]
        self.assertEqual(original_product, invoice.invoice_line[0].name)
        self.assertEqual(original_partner, invoice.partner_id['name'])
        self.assertEqual(original_price, invoice.amount_untaxed)
        self.assertEqual(original_start_date, invoice2.date_invoice)

        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(self.uid, 'recurring.contract',
                                self.contract_id, 'contract_terminated',
                                self.cr)
        contract_term = contract.browse(self.cr, self.uid, self.contract_id)
        self.assertEqual(contract_term.state, 'terminated')

        original_total = contract_term.total_amount
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
        self.contract_group = self._create_group(
            'do_nothing', 1, 'month', self.partner_id1, 2,
            self.payment_term_id, '137 option payement')

        self.contract_id = self._create_contract(
            datetime.today() + timedelta(days=2), self.contract_group,
            datetime.today() + timedelta(days=2))
        self.contract_line_id1 = self._create_contract_line(self.contract_id,
                                                            '75.0')
        self.contract_id2 = self._create_contract(
            datetime.today() + timedelta(days=2),
            self.contract_group, datetime.today() + timedelta(days=2))
        self.contract_line_id2 = self._create_contract_line(
            self.contract_id2, '85.0')
        self.assertTrue(self.contract_id2)

        contract_obj = self.registry('recurring.contract')
        contract_line_obj = self.registry('recurring.contract.line')
        contract_line_1 = contract_line_obj.browse(
            self.cr, self.uid, self.contract_line_id1)
        contract_line_2 = contract_line_obj.browse(
            self.cr, self.uid, self.contract_line_id2)

        original_price1 = contract_line_1.subtotal
        original_price2 = contract_line_2.subtotal

        # We put the contracts in active state to generate invoices
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            self.contract_id, 'contract_validated', self.cr)
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            self.contract_id2, 'contract_validated', self.cr)
        contract_act2 = contract_obj.browse(
            self.cr, self.uid, self.contract_id2)
        self.assertEqual(contract_act2.state, 'active')
        invoicer_obj = self.registry('recurring.invoicer')
        invoicer_id = contract_act2.button_generate_invoices()
        invoicer = invoicer_obj.browse(self.cr, self.uid, invoicer_id)
        invoices = invoicer.invoice_ids
        nb_invoice = len(invoices)
        self.assertEqual(nb_invoice, 2)
        invoice_fus = invoices[0]
        self.assertEqual(
            original_price1 + original_price2, invoice_fus.amount_untaxed)

        # Changement of the payment option
        group_obj = self.registry('recurring.contract.group')
        group_obj.write(
            self.cr, self.uid, self.contract_group, {
                'change_method': 'clean_invoices',
                'recurring_value': 2,
                'recurring_unit': 'week',
                'advance_billing_months': 2,
            })
        new_invoicer_id = invoicer_obj.search(self.cr, self.uid, [],
                                              order='id DESC')[0]
        new_invoicer = invoicer_obj.browse(self.cr, self.uid, new_invoicer_id)
        new_invoices = new_invoicer.invoice_ids
        nb_new_invoices = len(new_invoices)
        self.assertEqual(nb_new_invoices, 5)

        # Copy of one contract to test copy method()
        contract_obj.copy(
            self.cr, self.uid, self.contract_id2)
        contract_copied_id = contract_obj.search(self.cr, self.uid, [
            ('state', '=', 'draft'),
            ('partner_id', '=', self.partner_id1)], order='id desc')[0]
        self.assertTrue(contract_copied_id)
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            contract_copied_id, 'contract_validated', self.cr)
        contract_copied_act = contract_obj.browse(
            self.cr, self.uid, contract_copied_id)
        self.assertEqual(contract_copied_act.state, 'active')
        contract_copied_line = contract_copied_act.contract_line_ids[0]
        contract_line_obj.write(
            self.cr, self.uid, contract_copied_line.id, {
                'amount': 160.0,
            })
        new_price2 = contract_copied_line.subtotal
        invoicer_wizard_obj = self.registry('recurring.invoicer.wizard')
        invoicer_wiz_id = invoicer_wizard_obj.generate(
            self.cr, self.uid, [])
        invoicer_wiz = invoicer_wizard_obj.browse(
            self.cr, self.uid, invoicer_wiz_id['res_id'])
        new_invoices = invoicer_wiz.invoice_ids
        new_invoice_fus = new_invoices[0]
        self.assertEqual(new_price2, new_invoice_fus.amount_untaxed)

    def test_generated_invoice_third_scenario(self):
        """
            Creation of several contracts of the same group to test the case
            if we cancel one of the contracts if invoices are still correct.
        """
        # Creation of a group
        self.contract_group = self._create_group(
            'do_nothing', 1, 'month', self.partner_id, 1, self.payment_term_id)

        # Creation of three contracts with two lines each
        self.contract_id = self._create_contract(
            datetime.today().strftime(DF), self.contract_group,
            datetime.today().strftime(DF))
        self.contract_id2 = self._create_contract(
            datetime.today().strftime(DF), self.contract_group,
            datetime.today().strftime(DF))
        self.contract_id3 = self._create_contract(
            datetime.today().strftime(DF), self.contract_group,
            datetime.today().strftime(DF))

        self.contract_line_id0 = self._create_contract_line(
            self.contract_id, '10.0')
        self.contract_line_id1 = self._create_contract_line(
            self.contract_id, '20.0')
        self.contract_line_id2 = self._create_contract_line(
            self.contract_id2, '30.0')
        self.contract_line_id3 = self._create_contract_line(
            self.contract_id2, '40.0')
        self.contract_line_id4 = self._create_contract_line(
            self.contract_id3, '15.0')
        self.contract_line_id5 = self._create_contract_line(
            self.contract_id3, '25.0')

        contract = self.registry('recurring.contract')
        contract_obj = contract.browse(self.cr, self.uid, self.contract_id)
        contract_line = self.registry('recurring.contract.line')
        contract_line_obj0 = contract_line.browse(self.cr, self.uid,
                                                  self.contract_line_id0)
        contract_line_obj1 = contract_line.browse(self.cr, self.uid,
                                                  self.contract_line_id1)
        contract_line_obj2 = contract_line.browse(self.cr, self.uid,
                                                  self.contract_line_id2)
        contract_line_obj3 = contract_line.browse(self.cr, self.uid,
                                                  self.contract_line_id3)
        contract_line_obj4 = contract_line.browse(self.cr, self.uid,
                                                  self.contract_line_id4)
        contract_line_obj5 = contract_line.browse(self.cr, self.uid,
                                                  self.contract_line_id5)
        # Creation of data to test
        original_product = contract_line_obj0.product_id['name']
        original_partner = contract_obj.partner_id['name']
        original_price = sum([contract_line_obj0.subtotal,
                              contract_line_obj1.subtotal,
                              contract_line_obj2.subtotal,
                              contract_line_obj3.subtotal,
                              contract_line_obj4.subtotal,
                              contract_line_obj5.subtotal])
        original_start_date = contract_obj.start_date

        # We put all the contracts in active state
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            self.contract_id, 'contract_validated', self.cr)
        contract_obj = self.registry('recurring.contract')
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            self.contract_id2, 'contract_validated', self.cr)
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            self.contract_id3, 'contract_validated', self.cr)

        # Creation of a wizard to generate invoices
        invoicer_wizard_obj = self.registry('recurring.invoicer.wizard')
        invoicer_wiz_id = invoicer_wizard_obj.generate(
            self.cr, self.uid, [])
        invoicer_wiz = invoicer_wizard_obj.browse(
            self.cr, self.uid, invoicer_wiz_id['res_id'])
        invoices = invoicer_wiz.invoice_ids
        invoice = invoices[0]
        invoice2 = invoices[1]

        # We put the third contract in terminate state to see if
        # the invoice is well updated
        wf_service.trg_validate(
            self.uid, 'recurring.contract',
            self.contract_id3, 'contract_terminated', self.cr)
        contract_term = contract_obj.browse(
            self.cr, self.uid, self.contract_id3)
        self.assertEqual(contract_term.state, 'terminated')
        self.assertEqual(original_product, invoice.invoice_line[0].name)
        self.assertEqual(original_partner, invoice.partner_id['name'])
        self.assertEqual(
            original_price - contract_term.total_amount,
            invoice.amount_untaxed)
        self.assertEqual(original_start_date, invoice2.date_invoice)
