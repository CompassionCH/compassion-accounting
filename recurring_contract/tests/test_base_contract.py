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
import logging
import pdb
logger = logging.getLogger(__name__)


class test_base_contract(common.TransactionCase):

    def setUp(self):
        super(test_base_contract, self).setUp()
        # Creation of an account
        account_obj = self.env['account.account']
        account_type_obj = self.env['account.account.type']
        account_type = account_type_obj.search([
            ('code', '=', 'receivable')]).ids[0]
        property_account_receivable = account_obj.search([
            ('type', '=', 'receivable'),
            ('user_type', '=', account_type)]).ids[0]
        account_type = account_type_obj.search([
            ('code', '=', 'payable')]).ids[0]
        property_account_payable = account_obj.search([
            ('type', '=', 'payable'),
            ('user_type', '=', account_type)]).ids[0]

        # Creation of partners
        partner_obj = self.env['res.partner']
        self.partners = partner_obj.create(
            {
                'name': 'Monsieur Client 137',
                'property_account_receivable': property_account_receivable,
                'property_account_payable': property_account_payable,
                'notify_email': 'none',
                'ref': '00001111',
            })
        self.partners += partner_obj.create(
            {
                'name': 'Monsieur Pumba',
                'property_account_receivable': property_account_receivable,
                'property_account_payable': property_account_payable,
                'notify_email': 'none',
                'ref': '00002222',
            })
        # Creation of payement terms
        payment_term_obj = self.env['account.payment.term']
        self.payment_term_id = payment_term_obj.search(
            [('name', '=', '15 Days')])[0].id

    def _create_contract(self, start_date, group_id, next_invoice_date,
                         other_vals=None, bool=False):
        """
            Create a contract. For that purpose we have created a partner
            to get his id
        """
        # Creation of a contract
        contract_obj = self.env['recurring.contract']
        group = self.env['recurring.contract.group'].browse(group_id)
        partner_id = group.partner_id.id
        vals = {
            'start_date': start_date,
            'partner_id': partner_id,
            'group_id': group_id,
            'next_invoice_date': next_invoice_date,
        }
        if bool:
            vals['correspondant_id'] = partner_id
        if other_vals:
            vals.update(other_vals)
        if other_vals['type'] not in ('O', 'G'):
            pdb.set_trace()
            contract = contract_obj.with_context(
                default_type=other_vals['type']).create(vals)
        else:
            contract = contract_obj.create(vals)
        return contract.id

    def _create_contract_line(self, contract_id, price, other_vals=None):
        """ Create contract's lines """
        contract_line_obj = self.env['recurring.contract.line']
        vals = {
            'product_id': 1,
            'amount': price,
            'contract_id': contract_id,
        }
        if other_vals:
            vals.update(other_vals)

        contract_line_id = contract_line_obj.create(vals).id
        return contract_line_id

    def _create_group(self, change_method, partner_id,
                      adv_biling_months, payment_term_id, ref=None,
                      other_vals=None):
        """
            Create a group with 2 possibilities :
                - ref is not given so it takes "/" default values
                - ref is given
        """
        group_obj = self.env['recurring.contract.group']
        group = group_obj.create(
            {'partner_id': partner_id})
        group_vals = {
            'change_method': change_method,
            'partner_id': partner_id,
            'advance_billing_months': adv_biling_months,
            'payment_term_id': payment_term_id,
        }
        if ref:
            group_vals['ref'] = ref
        if other_vals:
            group_vals.update(other_vals)
        group.write(group_vals)
        return group.id
