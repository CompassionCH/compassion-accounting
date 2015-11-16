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

import logging
from datetime import date
from openerp import fields
from openerp.tests import common

logger = logging.getLogger(__name__)


class test_base_contract(common.TransactionCase):

    def setUp(self):
        super(test_base_contract, self).setUp()

        self.invoicer_wizard_obj = self.env[
            'recurring.invoicer.wizard'].with_context(async_mode=False)

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
                'lang': 'en_US',
            })
        self.partners += partner_obj.create(
            {
                'name': 'Monsieur Pumba',
                'property_account_receivable': property_account_receivable,
                'property_account_payable': property_account_payable,
                'notify_email': 'none',
                'ref': '00002222',
                'lang': 'en_US',
            })
        self.partners += partner_obj.create({
            'name': 'Monsieur Bryan',
            'property_account_receivable': property_account_receivable,
            'property_account_payable': property_account_payable,
            'notify_email': 'always',
            'ref': '00003333',
            'lang': 'en_US',
        })
        # Creation of payement terms
        payment_term_obj = self.env['account.payment.term']
        self.payment_term_id = payment_term_obj.search(
            [('name', '=', '15 Days')])[0].id

        # Verify existing periods
        today = date.today()
        next_year = date(today.year + 1, 1, 1)
        end_next_year = date(next_year.year, 12, 31)
        fy_obj = self.env['account.fiscalyear']
        fiscal_year = fy_obj.search([
            ('date_start', '>=', fields.Date.to_string(next_year)),
            ('date_stop', '<=', fields.Date.to_string(end_next_year))])
        if not fiscal_year:
            fiscal_year = fy_obj.create({
                'name': 'Next year',
                'code': 'NEXTYR',
                'date_start': fields.Date.to_string(next_year),
                'date_stop': fields.Date.to_string(end_next_year),
            })
            fiscal_year.create_period()

    def _create_group(self, change_method, partner_id,
                      adv_biling_months, payment_term_id, ref=None,
                      other_vals=None):
        """
            Create a group with 2 possibilities :
                - ref is not given so it takes "/" default values
                - ref is given
        """
        group_obj = self.env['recurring.contract.group'].with_context(
            async_mode=False)
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
        group = group_obj.create(group_vals)
        return group

    def _create_contract(self, start_date, group, next_invoice_date,
                         other_vals=None):
        """
            Create a contract. For that purpose we have created a partner
            to get his id
        """
        # Creation of a contract
        contract_obj = self.env['recurring.contract'].with_context(
            async_mode=False)
        partner_id = group.partner_id.id
        vals = {
            'start_date': start_date,
            'partner_id': partner_id,
            'group_id': group.id,
            'next_invoice_date': next_invoice_date,
        }
        if other_vals:
            vals.update(other_vals)
            if other_vals and 'type' in other_vals:
                contract_obj = contract_obj.with_context(
                    default_type=other_vals['type'])
        contract = contract_obj.create(vals)
        return contract

    def _create_contract_line(self, contract_id, price, other_vals=None):
        """ Create contract's lines """
        contract_line_obj = self.env['recurring.contract.line'].with_context(
            async_mode=False)
        vals = {
            'product_id': 1,
            'amount': price,
            'contract_id': contract_id,
        }
        if other_vals:
            vals.update(other_vals)

        contract_line = contract_line_obj.create(vals)
        return contract_line
