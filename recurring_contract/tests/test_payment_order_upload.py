from ast import literal_eval
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..models import account_payment_order

JOB_METHOD = "payment_order_post_and_reconcile"


@tagged("-at_install", "post_install")
class TestPaymentOrderUpload(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref(
            "account_payment_order.group_account_payment"
        )
        cls.journal = cls.company_data["default_journal_bank"]
        cls.inbound_mode = cls.env["account.payment.mode"].create(
            {
                "name": "Test Direct Debit",
                "bank_account_link": "variable",
                "payment_method_id": cls.env.ref(
                    "account.account_payment_method_manual_in"
                ).id,
                "company_id": cls.env.company.id,
                "variable_journal_ids": [(6, 0, cls.journal.ids)],
            }
        )
        partners = cls.env["res.partner"].create(
            [{"name": f"Debtor {i}"} for i in range(3)]
        )
        cls.invoices = cls.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": partner.id,
                    "payment_mode_id": cls.inbound_mode.id,
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "Donation",
                                "quantity": 1,
                                "price_unit": 100.0,
                                "tax_ids": [(5, 0, 0)],
                            },
                        )
                    ],
                }
                for partner in partners
            ]
        )
        cls.invoices.action_post()
        cls.env["account.invoice.payment.line.multi"].with_context(
            active_model="account.move", active_ids=cls.invoices.ids
        ).create({}).run()
        cls.order = cls.invoices.line_ids.payment_line_ids.order_id
        cls.order.journal_id = cls.journal
        cls.order.draft2open()
        cls.order.open2generated()

    def _run_post_jobs(self):
        """Run the queued post-and-reconcile jobs in order, whichever queue
        the database has (queue_job, or queue_job_optional's replacement)."""
        if "queue.job" in self.env:
            jobs = self.env["queue.job"].search(
                [("method_name", "=", JOB_METHOD)], order="id"
            )
            chunks = [self.env[job.model_name].browse(job.record_ids) for job in jobs]
        else:
            jobs = self.env["queue.job.replacement"].search(
                [("job_function", "=", JOB_METHOD)], order="id"
            )
            chunks = [
                self.env[job.res_model].browse(literal_eval(job.res_ids))
                for job in jobs
            ]
        for chunk in chunks:
            chunk.payment_order_post_and_reconcile()
        return len(chunks)

    def test_small_order_is_uploaded_at_once(self):
        self.assertEqual(len(self.order.payment_ids), 3)
        self.order.generated2uploaded()
        self.assertEqual(self.order.state, "uploaded")
        self.assertEqual(set(self.order.payment_ids.mapped("state")), {"in_process"})
        self.assertEqual(set(self.invoices.mapped("payment_state")), {"in_payment"})

    def test_large_order_is_posted_in_background(self):
        with (
            patch.object(account_payment_order, "ASYNC_PAYMENT_THRESHOLD", 1),
            patch.object(account_payment_order, "PAYMENTS_PER_JOB", 1),
        ):
            self.order.generated2uploaded()
            # nothing is posted in the request: the order waits for its jobs
            self.assertEqual(self.order.state, "generated")
            self.assertEqual(set(self.order.payment_ids.mapped("state")), {"draft"})
            self.assertEqual(self._run_post_jobs(), 3)
        # the last chunk sets the order to uploaded
        self.assertEqual(self.order.state, "uploaded")
        self.assertTrue(self.order.date_uploaded)
        self.assertEqual(set(self.order.payment_ids.mapped("state")), {"in_process"})
        self.assertEqual(set(self.invoices.mapped("payment_state")), {"in_payment"})
