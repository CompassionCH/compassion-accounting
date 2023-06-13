from odoo import fields
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install', 'only_this')
class AccountInvoiceTestCase(AccountTestInvoicingCommon):
    """Unit tests of the methods implemented on the object account move"""
    def setUp(self):
        super(AccountInvoiceTestCase, self).setUp()
        self.invoice_model = self.env['account.move']
        self.invoice = self.invoice_model.create({
            'partner_id': self.partner_a.id,
            'name': 'Invoice 1',
            'move_type': 'out_invoice',
            'invoice_line_ids': [(0, 0, {'product_id': self.product_a.id, 'quantity': 1, 'price_unit': 10.0})]
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
        self.invoice.update_open_invoices(updt_val)
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
        self.invoice.update_open_invoices(updt_val)
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
        self.invoice.update_open_invoices(updt_val)
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
        result = self.invoice._build_invoices_data(invoice_date=invoice_date, ref=ref, pay_mode_id=pay_mode_id,
                                                   payment_term_id=payment_term_id, partner_id=partner_id)
        self.assertEqual(result.get('Invoice 1').get('date'), invoice_date)
        self.assertEqual(result.get('Invoice 1').get('payment_reference'), ref)
        self.assertEqual(result.get('Invoice 1').get('payment_mode_id'), pay_mode_id)
        self.assertEqual(result.get('Invoice 1').get('invoice_payment_term_id'), payment_term_id)
        self.assertEqual(result.get('Invoice 1').get('partner_id'), partner_id)
