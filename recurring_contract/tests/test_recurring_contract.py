# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Albert SHENOUDA <albert.shenouda@efrei.net>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from openerp.tests import common
from datetime import datetime
from openerp import netsvc
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from openerp import netsvc
import logging
logger = logging.getLogger(__name__)


class test_recurring_contract(common.TransactionCase):
    """ 
        Test Project recurring contract. It's the first test file. 
        We are testing the first easier scenario : 
            - we are creating one contract
            - a payment option in which:
                - 1 invoice is generated every month
                - with 1 month of invoice generation in advance
        We are testing if invoices data are coherent with data in the 
        associate contract 
    """

    def setUp(self):
        super(test_recurring_contract, self).setUp()
        # Creation of a journal
        journal_obj = self.registry('account.journal')
        journal_id = journal_obj.write(self.cr, self.uid, 1, {
            'type': 'sale',
            'update_posted': True,
        })
        # Creation a partner 
        account_type = self.registry('account.account.type').write(self.cr, 
            self.uid, 1, {
                'close_method': 'unreconciled',
            })
        property_account_receivable = self.registry('account.account').write(
            self.cr, self.uid, 1, {
            'type': 'receivable',
            'user_type': 1,
        })
        property_account_payable = self.registry('account.account').write(
            self.cr, self.uid, 1, {
            'type': 'payable'
        })    
        partner = self.registry('res.partner')
        partner_id = partner.create(self.cr, self.uid, {
            'name': 'Monsieur Client 137',
            'property_account_receivable': 1,
            'property_account_payable': 1,
        })
        #Search of a product
        #product = self.registry('product.product')
        #product_id = []
        #product_id = product.create(self.cr, self.uid, {
         #   'name': 'Chocolat',
          #  'product_tmpl_id': 188,
        #})
        #Creation of payement term
        payment_term = self.registry('account.payment.term')
        payment_term_id = payment_term.create(self.cr, self.uid, {
            'name': '15 Days',
        })
        payment_term_line = self.registry('account.payment.term.line')
        payment_term_line_id = payment_term_line.create(self.cr, self.uid, {
            'days': 15,
            'payment_id': payment_term_id,
        })
        self.contract_group0 = self._create_group('do_nothing', 1, 
            'month', partner_id, 1, payment_term_id)
            
        self.contract_id = self._create_contract(
            datetime.today().strftime(DF), self.contract_group0, 
            datetime.today().strftime(DF))
        self.contract_line_id = self._create_contract_line(self.contract_id,
            '40.0')


    def _create_contract(self, start_date, group_id, next_invoice_date):
        """ 
            Create a contract. For that purpose we have created a partner 
            to get his id
        """
        journal_obj = self.registry('account.journal')
        journal_id = journal_obj.write(self.cr, self.uid, 1, {
            'type': 'sale',
            'update_posted': True,
        })
        # Creation a partner 
        account_type = self.registry('account.account.type').write(self.cr, 
            self.uid, 1, {
                'close_method': 'unreconciled',
            })
        property_account_receivable = self.registry('account.account').write(
            self.cr, self.uid, 1, {
            'type': 'receivable',
            'user_type': 1,
        })
        property_account_payable = self.registry('account.account').write(
            self.cr, self.uid, 1, {
            'type': 'payable'
        })
        # Creation a partner 
        partner = self.registry('res.partner')
        partner_id = partner.create(self.cr, self.uid, {
            'name': 'Monsieur Client 137',
            'property_account_receivable': 1,
            'property_account_payable': 1,
        })
        # Creation of a contract
        contract_obj = self.registry('recurring.contract')
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
        group = self.registry('recurring.contract.group')
        group_id = group.create(self.cr, self.uid, {
            'partner_id': partner_id,
            })
        group_obj = group.browse(self.cr, self.uid, group_id)    
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
        group_obj.write(group_vals)
        return group_id

    def test_generated_invoice(self):
        """ 
            Test the button_generate_invoices method which call a lot of 
            other methods like generate_invoice(). We are testing the coherence 
            of data when a contract generate invoice(s) 
        """
        contract = self.registry('recurring.contract')
        contract_obj = contract.browse(self.cr, self.uid, self.contract_id)
        contract_line = self.registry('recurring.contract.line')
        contract_line_obj = contract_line.browse(self.cr, self.uid, 
            self.contract_line_id)

        original_product = contract_line_obj.product_id['name']
        original_partner = contract_obj.partner_id['name']
        original_price = contract_line_obj.subtotal
        original_start_date = contract_obj.start_date

        # To generate invoices, the contract must be "active"
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(self.uid, 'recurring.contract',
            self.contract_id, 'contract_validated', self.cr)
        contract_act = contract.browse(self.cr, self.uid, self.contract_id)
        self.assertEqual(contract_act.state, 'active')
        invoicer = self.registry('recurring.invoicer')
        invoicer_id = contract_act.button_generate_invoices()
        invoicer_obj = invoicer.browse(self.cr, self.uid, invoicer_id)
        invoices = invoicer_obj.invoice_ids
        nb_invoice = len(invoices)
        self.assertEqual(nb_invoice, 2) # 2 invoices must be generated with our 
                                        # parameters
        invoice = invoices[0]
        invoice2 = invoices[1]
        self.assertEqual(original_product, invoice.invoice_line[0].name)
        self.assertEqual(original_partner, invoice.partner_id['name'])
        self.assertEqual(original_price, invoice.amount_untaxed)
        self.assertEqual(original_start_date, invoice2.date_invoice)

        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(self.uid, 'recurring.contract',
            self.contract_id, 'contract_terminated', self.cr)
        contract_term = contract.browse(self.cr, self.uid, self.contract_id)
        self.assertEqual(contract_term.state, 'terminated')

        """original_total = contract_term.total_amount
        self.assertEqual(original_total, invoice.amount_total)"""

