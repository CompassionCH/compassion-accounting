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
import logging


logger = logging.getLogger(__name__)


class test_recurring_contract(common.TransactionCase):

    """ Test Project recurring contract """

    def setUp(self):
        super(test_recurring_contract, self).setUp()
        self.contract_group0 = self._create_group('Nothing', 1, 
            'Month(s)', 'Monsieur Client 137', 1, '15 Days')
        self.contract_group1 = self._create_group('Nothing', 1, 
            'Month(s)', 'Monsieur Client 137', 2, "137 option payement",
            '15 Days')
            
        self.contract_id0 = self._create_contract('CON00008',
            '05/29/2015', '/')
        self.contract_line_id0 = self._create_contract_line('Chocolat', '40.0')
        
        self.contract_id1 = self._create_contract('CON00009',
            '06/01/2015', '137 option payement')
        self.contract_line_id1 = self._create_contract_line('Service', '75.0')
       
        self.contract_id2 = self._create_contract('CON000010',
            '06/01/2015', '137 option payement')
        self.contract_line_id2 = self._create_contract_line('Service', '85.0')

        
    def _create_contract(self, contract_name, start_date, group_id):

        # Creation a partner 
        partner = self.registry('res.partner')
        partner_id = partner.create(self.cr, self.uid, {
            'name': 'Monsieur Client 137',
        })

        # Creation of a contract
        contract_obj = self.registry('recurring.contract')
        contract_id = contract_obj.create(self.cr, self.uid, {
            'reference': contract_name,
            'start_date': start_date,
            'partner_id': partner_id,
            'group_id': group_id,
        })

        return contract_id

    def _create_contract_line(self, product_name, price):
        contract_line_obj = self.registry('recurring.contract.line')
        contract_line_id = contract_line_obj.create(self.cr, self.uid, {
            'product_id': product_name,
            'amount': price,
            'contract_id': self.contract_id,
        })
        return contract_line_id

    def _create_group(self, change_method, rec_value, rec_unit, partner_id,
           adv_biling_months, ref=None, payment_term):
        group = self.registry('recurring.contract.group')
        group_id = group.create(self.cr, self.uid, 
                                [('partner_id', '=', partner_id)])
        group_id.write(self.cr, self.uid, group_id, group_vals)
           
        group_vals = {
            'change_method': change_method,
            'recurring_value': rec_value,
            'recurring_unit': rec_unit,
            'partner_id': partner_id,
            'advance_billing_months': adv_biling_months,
            'payment_term_id': payment_term,
            }
        if ref:
            group_vals['ref'] = ref
        
        return group_id
    
    def test_generated_invoice(self, contract):
    
        original_product = contract.product_id
        original_partner = contract.partner_id
        original_price = contract.subtotal
        original_total = contract.total_amount
        original_start_date = contract.start_date
        
        

        