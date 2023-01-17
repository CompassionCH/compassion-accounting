import logging
from datetime import date
from unittest.mock import MagicMock

from odoo import fields
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install', 'only_this')
class AccountInvoiceTestCase(AccountTestInvoicingCommon):
    def setUp(self):
        super(AccountInvoiceTestCase, self).setUp()
        self.invoice_model = self.env['account.move']
        self.invoice = self.invoice_model.create({
            'partner_id': self.partner_a.id,
            'name': 'Invoice 1',
            'move_type': 'out_invoice',
            'invoice_line_ids': [(0, 0, {'product_id': self.product_a.id, 'quantity': 1, 'price_unit': 10.0})]
        })
        self.group = self.env['recurring.contract.group'].create({
            'advance_billing_months': 1,
            'partner_id': self.env.ref('base.res_partner_1').id,
            'recurring_unit': 'month',
            'recurring_value': 1,
            'ref': 'Test Group'
        })
        self.payment_mode = self.env['account.payment.mode'].create({
            'name': 'Test Payment Mode',
            'payment_type': 'inbound',
            'bank_account_link': 'fixed',
            'payment_method_id': self.env['account.payment.method'].search([], limit=1).id,
            'fixed_journal_id': self.env['account.journal'].search([('company_id', '=', self.env.user.company_id.id)],
                                                                   limit=1).id
        })
        # Create a new contract with a set invoice_day
        self.contract = self.env['recurring.contract'].create({
            'reference': 'Test Contract',
            'partner_id': self.partner_a.id,
            'group_id': self.group.id,
            'pricelist_id': self.env.ref('product.list0').id,
            'contract_line_ids': [(0, 0, {'product_id': self.product_a.id, 'amount': 10.0, 'quantity': 1})],
            'invoice_day': '15',
        })

    def test_update_invoices(self):
        """
        Test updating the invoice with a new price
        Asserts that the total amount is correct after the update
        """
        updt_val = {
            self.invoice.name: {
                'invoice_line_ids': [(1, self.invoice.invoice_line_ids[0].id, {'price_unit': 20.0})]
            }
        }
        self.invoice.update_invoices(updt_val)
        self.assertEqual(self.invoice.amount_total, 20.0)

    def test_update_invoices_cancel_invoice(self):
        """
        Test updating the invoice with a new price and check if it's canceled
        Asserts that the total amount is correct after the update and that the invoice state is 'cancel'
        """
        updt_val = {
            self.invoice.name: {
                'invoice_line_ids': [(1, self.invoice.invoice_line_ids[0].id, {'price_unit': 0.0})]
            }
        }
        self.invoice.update_invoices(updt_val)
        self.assertEqual(self.invoice.state, 'cancel')

    def test_update_invoices_post_invoice(self):
        """
        Test updating the invoice with a new price and check if it's posted
        Asserts that the total amount is correct after the update and that the invoice state is 'posted'
        """
        updt_val = {
            self.invoice.name: {
                'invoice_line_ids': [(1, self.invoice.invoice_line_ids[0].id, {'price_unit': 100.0})]
            }
        }
        self.invoice.update_invoices(updt_val)
        self.assertEqual(self.invoice.amount_total, 100.0)
        self.assertEqual(self.invoice.state, 'posted')

    def test_build_invoice_data(self):
        """
       Test building the invoice data dictionary
       Asserts that the returned dictionary contains the correct invoice data
       """
        invoice_date = fields.Date.today()
        ref = "12345"
        pay_mode_id = self.payment_mode.id
        payment_term_id = self.env['account.payment.term'].search([], limit=1).id
        partner_id = self.env['res.partner'].search([], limit=1).id
        result = self.invoice._build_invoice_data(invoice_date=invoice_date, ref=ref, pay_mode_id=pay_mode_id,
                                                  payment_term_id=payment_term_id, partner_id=partner_id)
        self.assertEqual(result.get('Invoice 1').get('date'), invoice_date)
        self.assertEqual(result.get('Invoice 1').get('payment_reference'), ref)
        self.assertEqual(result.get('Invoice 1').get('payment_mode_id'), pay_mode_id)
        self.assertEqual(result.get('Invoice 1').get('invoice_payment_term_id'), payment_term_id)
        self.assertEqual(result.get('Invoice 1').get('partner_id'), partner_id)
