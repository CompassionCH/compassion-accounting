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
from datetime import datetime
from openerp import netsvc
import logging
logger = logging.getLogger(__name__)


class test_split_invoice(common.TransactionCase):
    """ Test Project split invoice. 2 cases are tested :
           - open invoices
           - draft invoices
        This test check if the original invoice is well splitted in 2 invoices
        with the same informations and if the amount are matched """
    def setUp(self):
        super(test_split_invoice, self).setUp()
        self.invoice_id = self._create_invoice('SAJ/2015/0002')
        self.invoice_id1 = self._create_invoice('SAJ/2015/0003')
        self.invoice_line_id1 = self._create_invoice_line(
            'service 1', '70.0', self.invoice_id)
        self.invoice_line_id2 = self._create_invoice_line(
            'service 2', '80.0', self.invoice_id)
        self.invoice_line_id11 = self._create_invoice_line(
            'service 11', '40.0', self.invoice_id1)
        self.invoice_line_id22 = self._create_invoice_line(
            'service 22', '50.0', self.invoice_id1)

    def test_open_invoice(self):
        """ Run test for invoice in 'open' state """
        self.assertTrue(self.invoice_id)
        invoice_obj = self.registry('account.invoice')
        invoice = invoice_obj.browse(self.cr, self.uid, self.invoice_id)
        self.assertTrue(invoice)
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(
            self.uid, 'account.invoice', self.invoice_id,
            'invoice_open', self.cr)
        wizard_obj = self.registry('account.invoice.split.wizard')
        wizard_id = wizard_obj.create(
            self.cr, self.uid, dict(), context={
                'active_id': self.invoice_id})

        original_amount = invoice.amount_total
        original_name = invoice.name
        orginal_partner_id = invoice.partner_id.id
        original_invoice_date = invoice.date_invoice
        original_account = invoice.account_id.id
        original_journal = invoice.journal_id.id
        new_invoice_id = wizard_obj._write_lines(
            self.cr, self.uid, wizard_id, 'invoice_line_ids', [
                (1, self.invoice_line_id1, {'split': True})], "")
        new_invoice = invoice_obj.browse(self.cr, self.uid, new_invoice_id)
        wizard = wizard_obj.browse(self.cr, self.uid, wizard_id)
        # Test if the lines have been exactly copied
        self.assertEqual(wizard.invoice_id.id, self.invoice_id)
        self.assertNotEqual(wizard.invoice_id.id, new_invoice_id)
        self.assertEqual(wizard.invoice_id.name, original_name)
        self.assertEqual(new_invoice.name, original_name)
        self.assertEqual(
            wizard.invoice_id.partner_id.id, orginal_partner_id)
        self.assertEqual(
            new_invoice.partner_id.id, orginal_partner_id)
        self.assertEqual(
            wizard.invoice_id.date_invoice, original_invoice_date)
        self.assertEqual(
            new_invoice.date_invoice, original_invoice_date)
        self.assertEqual(
            wizard.invoice_id.account_id.id, original_account)
        self.assertEqual(
            new_invoice.account_id.id, original_account)
        self.assertEqual(
            wizard.invoice_id.journal_id.id, original_journal)
        self.assertEqual(
            new_invoice.journal_id.id, original_journal)
        self.assertEqual(
            original_amount,
            wizard.invoice_id.amount_total + new_invoice.amount_total
        )

    def test_draft_invoice(self):
        """ Run test for invoice in 'draft' state """
        self.assertTrue(self.invoice_id1)
        invoice_obj = self.registry('account.invoice')
        invoice = invoice_obj.browse(self.cr, self.uid, self.invoice_id1)
        self.assertTrue(invoice)

        wizard_obj = self.registry('account.invoice.split.wizard')
        wizard_id = wizard_obj.create(
            self.cr, self.uid, dict(), context={
                'active_id': self.invoice_id1})

        original_amount = invoice.amount_total
        original_name = invoice.name
        orginal_partner_id = invoice.partner_id.id
        original_invoice_date = invoice.date_invoice
        original_account = invoice.account_id.id
        original_journal = invoice.journal_id.id
        new_invoice_id = wizard_obj._write_lines(
            self.cr, self.uid, wizard_id, 'invoice_line_ids', [
                (1, self.invoice_line_id1, {'split': True})], "")
        new_invoice = invoice_obj.browse(self.cr, self.uid, new_invoice_id)
        wizard = wizard_obj.browse(self.cr, self.uid, wizard_id)
        # Test if the lines have been exactly copied
        self.assertEqual(wizard.invoice_id.id, self.invoice_id1)
        self.assertNotEqual(wizard.invoice_id.id, new_invoice_id)
        self.assertEqual(wizard.invoice_id.name, original_name)
        self.assertEqual(new_invoice.name, original_name)
        self.assertEqual(
            wizard.invoice_id.partner_id.id, orginal_partner_id)
        self.assertEqual(
            new_invoice.partner_id.id, orginal_partner_id)
        self.assertEqual(
            wizard.invoice_id.date_invoice, original_invoice_date)
        self.assertEqual(
            new_invoice.date_invoice, original_invoice_date)
        self.assertEqual(
            wizard.invoice_id.account_id.id, original_account)
        self.assertEqual(
            new_invoice.account_id.id, original_account)
        self.assertEqual(
            wizard.invoice_id.journal_id.id, original_journal)
        self.assertEqual(
            new_invoice.journal_id.id, original_journal)
        self.assertEqual(
            original_amount,
            wizard.invoice_id.amount_total + new_invoice.amount_total
        )

    def _create_invoice(self, invoice_name):
        """ Set the update_posted to True to make invoice cancelable """
        journal_obj = self.registry('account.journal')
        journal_obj.write(self.cr, self.uid, 1, {
            'update_posted': True,
        })
        partner_obj = self.registry('res.partner')
        partner_id = partner_obj.create(self.cr, self.uid, {
            'name': 'Kevin',
        })
        account_id = self.registry('account.account').search(
            self.cr, self.uid, [('type', '=', 'receivable')])[0]
        invoice_obj = self.registry('account.invoice')
        invoice_id = invoice_obj.create(self.cr, self.uid, {
            'name': invoice_name,
            'account_id': account_id,
            'currency_id': 1,
            'journal_id': 1,
            'partner_id': partner_id,
            'date_invoice': datetime.today()
        })
        return invoice_id

    def _create_invoice_line(self, description, amount, invoice_id):
        """ Create invoice's lines """
        invoice_line_obj = self.registry('account.invoice.line')
        invoice_line_id = invoice_line_obj.create(self.cr, self.uid, {
            'name': description,
            'price_subtotal': amount,
            'invoice_id': invoice_id,
        })
        return invoice_line_id
