# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
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
        self.contract_id0 = self._create_contract(
            'CON00008', '137 option payment')
        self.contract_line_id = self._create_contract_line('Chocolat', '40.0')
        self.contract_id1 = self._create_contract(
            'CON00009', '137 option payement')
        self.contract_line_id = self._create_contract_line('Service', '75.0')
        self.contract_id2 = self._create_contract(
            'CON000010', '137 option payement')
        self.contract_line_id = self._create_contract_line('Service', '85.0')

        
    def _create_contract(self, contract_name, group_name):

        # Creation a partner 
        partner = self.registry('res.partner')
        partner_id = partner.create(self.cr, self.uid, {
            'name': 'Monsieur Client 137',

        })
        
        # Creation a group
        group = self.registry('recurring.contract.group')
        group_id = group.create(self.cr, self.uid, 
                                [('partner_id', '=', partner_id)])
        group_obj = group_id.write(self.cr, self.uid, group_id {
            'ref': group_name,            
        })

        # Creation of a contract
        contract_obj = self.registry('recurring.contract')
        contract_id = contract_obj.create(self.cr, self.uid, {
            'reference': contract_name,
            'start_date': '06/01/2015',
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

    def _test_write_lines(self, invoice):
        # Test if the invoice has been copied

        original_amount = invoice.amount_total
        original_name = invoice.name
        original_partner = invoice.partner_id
        original_invoice_date = invoice.date_invoice
        original_account = invoice.account_id
        original_journal = invoice.journal_id

        wizard_obj = self.registry('account.invoice.split.wizard')

        wizard_id = wizard_obj.create(
            self.cr, self.uid, dict(), context={
                'active_id': self.invoice_id})

        wizard = wizard_obj.browse(self.cr, self.uid, wizard_id)

        new_invoice_id = wizard_obj._write_lines(
            self.cr, self.uid, wizard_id, 'invoice_line_ids', [
                (1, self.invoice_line_id1, {'split': True})], "")

        invoice_obj = self.registry('account.invoice')

        new_invoice = invoice_obj.browse(self.cr, self.uid, new_invoice_id)

        # Test if the lines have been exactly copied

        self.assertEqual(wizard.invoice_id.id, self.invoice_id)
        self.assertNotEqual(wizard.invoice_id.id, new_invoice_id)
        self.assertEqual(wizard.invoice_id.name, original_name)
        self.assertEqual(
            wizard.invoice_id.partner_id, original_partner)
        self.assertEqual(
            wizard.invoice_id.date_invoice, original_invoice_date)
        self.assertEqual(
            wizard.invoice_id.account_id, original_account)
        self.assertEqual(
            wizard.invoice_id.journal_id, original_journal)
        self.assertEqual(
            original_amount,
            wizard.invoice_id.amount_total + new_invoice.amount_total
        )

    def test_open_invoice(self):

        # test for invoice in 'open' state

        self.assertTrue(self.invoice_id)
        invoice_obj = self.registry('account.invoice')
        invoice = invoice_obj.browse(self.cr, self.uid, self.invoice_id)

        self.assertTrue(invoice)

        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(
            self.uid, 'account.invoice', self.invoice_id,
            'invoice_open', self.cr)

        self._test_write_lines(invoice)

    def test_draft_invoice(self):

        # test for invoice in 'draft' state

        self.assertTrue(self.invoice_id)
        invoice_obj = self.registry('account.invoice')
        invoice = invoice_obj.browse(self.cr, self.uid, self.invoice_id)

        self.assertTrue(invoice)
        self._test_write_lines(invoice)
