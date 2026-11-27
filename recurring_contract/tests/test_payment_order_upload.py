from contextlib import ExitStack
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
        cls.payments = cls.order.payment_ids.sorted("id")

    def setUp(self):
        super().setUp()
        if "queue.job" in self.env:
            self.skipTest("These tests run the queue_job_optional replacement queue")
        # one payment per job, so that 3 payments make a chain of 3 jobs
        stack = ExitStack()
        stack.enter_context(
            patch.object(account_payment_order, "ASYNC_PAYMENT_THRESHOLD", 1)
        )
        stack.enter_context(patch.object(account_payment_order, "PAYMENTS_PER_JOB", 1))
        self.addCleanup(stack.close)

    def _jobs(self):
        return self.env["queue.job.replacement"].search(
            [("job_function", "=", JOB_METHOD)], order="id"
        )

    def _run_jobs(self, jobs):
        """Run the given jobs with the real runner (own cursor per job, a
        chained job only after its parent is done), never other jobs."""
        job_class = type(self.env["queue.job.replacement"])
        search = job_class.search

        def only_these_jobs(model, domain, *args, **kwargs):
            return search(model, [*domain, ("id", "in", jobs.ids)], *args, **kwargs)

        self.env.flush_all()
        # the runner opens a cursor of its own: in test mode, it shares the
        # test transaction
        self.registry.enter_test_mode(self.cr)
        try:
            with patch.object(job_class, "search", only_these_jobs):
                for _job in jobs:
                    self.env["queue.job.replacement"].sudo().cron_run_jobs()
        finally:
            self.registry.leave_test_mode()
        self.env.invalidate_all()

    def _assert_uploaded(self):
        self.assertEqual(self.order.state, "uploaded")
        self.assertTrue(self.order.date_uploaded)
        self.assertEqual(set(self.payments.mapped("state")), {"in_process"})
        self.assertEqual(set(self.invoices.mapped("payment_state")), {"in_payment"})

    def test_small_order_is_uploaded_at_once(self):
        with patch.object(account_payment_order, "ASYNC_PAYMENT_THRESHOLD", 100):
            self.order.generated2uploaded()
        self.assertFalse(self._jobs())
        self._assert_uploaded()

    def test_large_order_is_posted_in_chained_jobs(self):
        self.order.generated2uploaded()
        # nothing is posted in the request: the order waits for its jobs
        self.assertEqual(self.order.state, "generated")
        self.assertEqual(set(self.payments.mapped("state")), {"draft"})
        jobs = self._jobs()
        self.assertEqual(len(jobs), 3)
        self.assertFalse(jobs[0].parent_job_id)
        self.assertEqual(jobs[1].parent_job_id, jobs[0])
        self.assertEqual(jobs[2].parent_job_id, jobs[1])
        self._run_jobs(jobs)
        self.assertEqual(set(jobs.mapped("state")), {"done"})
        self._assert_uploaded()

    def test_failed_chunk_then_new_upload(self):
        """A failing chunk stops the chain and leaves the order generated;
        a new upload only queues the payments still to process."""
        self.order.generated2uploaded()
        first_jobs = self._jobs()
        failing = self.payments[1]
        payment_class = type(self.env["account.payment"])
        action_post = payment_class.action_post

        def action_post_failing(payments):
            if failing in payments:
                raise ValueError("Simulated posting error")
            return action_post(payments)

        with (
            patch.object(payment_class, "action_post", action_post_failing),
            self.assertLogs(
                "odoo.addons.queue_job_optional.models.queue_job_replacement",
                level="ERROR",
            ),
        ):
            self._run_jobs(first_jobs)
        self.assertEqual(first_jobs.mapped("state"), ["done", "failed", "pending"])
        self.assertEqual(self.order.state, "generated")
        self.assertEqual(self.payments[0].state, "in_process")
        self.assertEqual(self.payments[1:].mapped("state"), ["draft", "draft"])

        self.order.generated2uploaded()
        new_jobs = self._jobs() - first_jobs
        self.assertEqual(len(new_jobs), 2)
        self._run_jobs(new_jobs)
        self._assert_uploaded()

    def test_posted_but_unreconciled_payment_is_reconciled(self):
        """A payment posted by hand before the upload still gets reconciled
        with its invoice."""
        self.payments[0].action_post()
        self.assertEqual(self.invoices[0].payment_state, "not_paid")
        self.order.generated2uploaded()
        jobs = self._jobs()
        self.assertEqual(len(jobs), 3)
        self._run_jobs(jobs)
        self._assert_uploaded()

    def test_nothing_left_to_do_is_uploaded_at_once(self):
        for payment in self.payments:
            payment.action_post()
            payment._payment_order_lines_to_reconcile().reconcile()
        self.order.generated2uploaded()
        self.assertFalse(self._jobs())
        self._assert_uploaded()
