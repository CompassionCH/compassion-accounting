##############################################################################
#
#    Copyright (C) 2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Albert SHENOUDA <albert.shenouda@efrei.net>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo.tests import common
from datetime import datetime
from odoo import netsvc
import logging
logger = logging.getLogger(__name__)


class TestSplitInvoice(common.TransactionCase):
    """ Test Project split invoice. 2 cases are tested :
           - open invoices
           - draft invoices
        This test check if the original invoice is well splitted in 2 invoices
        with the same informations and if the amount are matched """
    def setUp(self):
        super().setUp()
        self.invoice_id = self._create_invoice('SAJ/2015/0002')
        self.invoice_id1 = self._create_invoice('SAJ/2015/0003')
        self.invoice_line_id1 = self._create_invoice_line(
            'service 1', 70.0, self.invoice_id)
        self.invoice_line_id2 = self._create_invoice_line(
            'service 2', 80.0, self.invoice_id)
        self.invoice_line_id11 = self._create_invoice_line(
            'service 11', 40.0, self.invoice_id1)
        self.invoice_line_id22 = self._create_invoice_line(
            'service 22', 50.0, self.invoice_id1)

    def test_open_invoice(self):
        """ Run test for invoice in 'open' state """
        self.assertTrue(self.invoice_id)
        invoice_obj = self.env['account.invoice']
        invoice = invoice_obj.browse(self.invoice_id)
        self.assertTrue(invoice)
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(
            self.uid, 'account.invoice', self.invoice_id,
            'invoice_open', self.cr)
        wizard_obj = self.env['account.invoice.split.wizard'].with_context(
            {'active_id': self.invoice_id})
        wizard = wizard_obj.create({})

        original_amount = invoice.amount_total
        original_name = invoice.name
        original_partner_id = invoice.partner_id.id
        original_invoice_date = invoice.date_invoice
        original_account = invoice.account_id.id
        original_journal = invoice.journal_id.id
        wizard.write(
            {'invoice_line_ids': [(4, self.invoice_line_id1)]})
        invoice_new = wizard.split_invoice()
        invoice = invoice_obj.browse(self.invoice_id)
        # Test if the lines have been exactly copied
        self.assertEqual(invoice.name, original_name)
        self.assertEqual(
            invoice.partner_id.id, original_partner_id)
        self.assertEqual(
            wizard.invoice_line_ids[0].invoice_id.date_invoice,
            original_invoice_date)
        self.assertEqual(
            invoice.date_invoice, original_invoice_date)
        self.assertEqual(
            wizard.invoice_line_ids[0].invoice_id.account_id.id,
            original_account)
        self.assertEqual(
            invoice.account_id.id, original_account)
        self.assertEqual(
            wizard.invoice_line_ids[0].invoice_id.journal_id.id,
            original_journal)
        self.assertEqual(
            invoice.journal_id.id, original_journal)
        self.assertEqual(
            original_amount,
            invoice_new.amount_total + invoice.amount_total
        )

    def test_draft_invoice(self):
        """ Run test for invoice in 'draft' state """
        self.assertTrue(self.invoice_id1)
        invoice_obj = self.env['account.invoice']
        invoice = invoice_obj.browse(self.invoice_id1)
        self.assertTrue(invoice)

        wizard_obj = self.env['account.invoice.split.wizard'].with_context(
            {'active_id': self.invoice_id1})
        wizard = wizard_obj.create({})

        original_amount = invoice.amount_total
        original_name = invoice.name
        orginal_partner_id = invoice.partner_id.id
        original_invoice_date = invoice.date_invoice
        original_account = invoice.account_id.id
        original_journal = invoice.journal_id.id
        wizard.write({
            'invoice_line_ids': [(4, self.invoice_line_id11)]})
        invoice_new = wizard.split_invoice()
        invoice = invoice_obj.browse(self.invoice_id1)
        # Test if the lines have been exactly copied
        self.assertEqual(invoice.name, original_name)
        self.assertEqual(
            wizard.invoice_line_ids[0].invoice_id.partner_id.id,
            orginal_partner_id)
        self.assertEqual(
            invoice.partner_id.id, orginal_partner_id)
        self.assertEqual(
            wizard.invoice_line_ids[0].invoice_id.date_invoice,
            original_invoice_date)
        self.assertEqual(
            invoice.date_invoice, original_invoice_date)
        self.assertEqual(
            wizard.invoice_line_ids[0].invoice_id.account_id.id,
            original_account)
        self.assertEqual(
            invoice.account_id.id, original_account)
        self.assertEqual(
            wizard.invoice_line_ids[0].invoice_id.journal_id.id,
            original_journal)
        self.assertEqual(
            invoice.journal_id.id, original_journal)
        self.assertEqual(
            original_amount,
            invoice_new.amount_total + invoice.amount_total
        )

    def _create_invoice(self, invoice_name):
        """ Set the update_posted to True to make invoice cancelable """
        journal_obj = self.env['account.journal']
        journal = journal_obj.search([('id', '=', 1)])
        journal.write({
            'update_posted': True,
        })
        partner_obj = self.env['res.partner']
        partner_id = partner_obj.create({
            'name': 'Kevin',
        }).id
        account_id = self.env['account.account'].search(
            [('internal_type', '=', 'receivable')])[0].id
        invoice_obj = self.env['account.invoice']
        invoice_id = invoice_obj.create({
            'name': invoice_name,
            'account_id': account_id,
            'currency_id': 1,
            'journal_id': 1,
            'partner_id': partner_id,
            'date_invoice': datetime.today()
        }).id
        return invoice_id

    def _create_invoice_line(self, description, amount, invoice_id):
        """ Create invoice's lines """
        invl_obj = self.env['account.invoice.line'].with_context(
            journal_id=1)
        invoice_line_id = invl_obj.create({
            'name': description,
            'price_unit': amount,
            'invoice_id': invoice_id,
            'account_id': invl_obj._default_account()
        }).id
        return invoice_line_id
