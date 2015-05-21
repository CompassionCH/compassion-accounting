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


class test_split_invoice(common.TransactionCase):

    """ Test Project split invoice """

    def setUp(self):
        super(test_split_invoice, self).setUp()
        self.invoice_id = self._create_invoice('SAJ/2015/0002')
        self.invoice_line_id1 = self._create_invoice_line('service 1', '70.0')
        self.invoice_line_id2 = self._create_invoice_line('service 2', '80.0')

    def _create_invoice(self, invoice_name):
        partner = self.registry('res.partner')
        partner_id = partner.create(self.cr, self.uid, {
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

    def _create_invoice_line(self, description, amount):
        invoice_line_obj = self.registry('account.invoice.line')
        invoice_line_id = invoice_line_obj.create(self.cr, self.uid, {
            'name': description,
            'price_subtotal': amount,
            'invoice_id': self.invoice_id,
        })
        return invoice_line_id

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
