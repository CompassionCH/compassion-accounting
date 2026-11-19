from odoo import fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestLockedInvoices(AccountTestInvoicingCommon):
    def test_sale_lock_date_protects_invoices(self):
        """Invoices of a locked sale period are never modified."""
        old = self.init_invoice(
            "out_invoice", invoice_date="2020-01-15", amounts=[100], post=True
        )
        new = self.init_invoice(
            "out_invoice", invoice_date=fields.Date.today(), amounts=[100], post=True
        )
        self.env.company.sale_lock_date = "2020-12-31"
        open_lines, locked = self.env["recurring.contract"]._split_locked_invoices(
            (old | new).invoice_line_ids
        )
        self.assertEqual(locked, old)
        self.assertEqual(open_lines.move_id, new)
