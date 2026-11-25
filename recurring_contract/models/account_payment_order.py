##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import models

# Above this number of payments, posting and reconciliation is done in
# background jobs, to avoid hitting the request time limit (the reconcile
# hooks trigger the contract invoice_paid logic, which is slow).
ASYNC_PAYMENT_THRESHOLD = 100
PAYMENTS_PER_JOB = 50


class AccountPaymentOrder(models.Model):
    _inherit = "account.payment.order"

    def generated2uploaded(self):
        if self.env.context.get("payment_order_posted_by_jobs"):
            return super().generated2uploaded()
        async_orders = self.filtered(
            lambda o: len(o.payment_ids) > ASYNC_PAYMENT_THRESHOLD
        )
        for order in async_orders:
            todo = order.payment_ids._payment_order_todo()
            if not todo:
                # Everything was already posted and reconciled
                order.with_context(
                    payment_order_posted_by_jobs=True
                ).generated2uploaded()
                continue
            todo.with_delay_sh(
                "payment_order_post_and_reconcile",
                split=PAYMENTS_PER_JOB,
                chain=True,
                description=f"Post and reconcile payments of {order.name}",
            )
            order.message_post(
                body=self.env._(
                    "%(count)s payments are being posted in background jobs. "
                    "The order will be set to uploaded once they are all posted.",
                    count=len(todo),
                )
            )
        super(AccountPaymentOrder, self - async_orders).generated2uploaded()
        if async_orders:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "info",
                    "message": self.env._(
                        "Payments are posted in background. The order will be "
                        "set to uploaded when finished."
                    ),
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }
        return True

    def post_and_reconcile(self):
        if self.env.context.get("payment_order_posted_by_jobs"):
            # Payments were already posted and reconciled by the jobs
            return
        return super().post_and_reconcile()


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _payment_order_lines_to_reconcile(self):
        """The unreconciled lines of the payment and of the paid items."""
        self.ensure_one()
        return (
            self.payment_line_ids.move_line_id
            + self.move_id.line_ids.filtered(
                lambda x: x.account_id == self.destination_account_id
            )
        ).filtered(lambda line: not line.reconciled)

    def _payment_order_todo(self):
        """The payments still to post, or posted but not reconciled (e.g. by
        a manual post or a job that failed after posting)."""
        return self.filtered(
            lambda p: p.state == "draft"
            or (
                p.state != "canceled"
                and not all(
                    p.move_id.line_ids.filtered(
                        lambda x, p=p: x.account_id == p.destination_account_id
                    ).mapped("reconciled")
                )
            )
        )

    def payment_order_post_and_reconcile(self):
        """Job method: same as account.payment.order.post_and_reconcile, for
        a chunk of payments. The last chunk sets the order to uploaded."""
        for payment in self._payment_order_todo():
            if payment.state == "draft":
                payment.action_post()
            lines = payment._payment_order_lines_to_reconcile()
            if len(lines) > 1:
                lines.reconcile()
        for order in self.payment_order_id:
            if (
                order.state == "generated"
                and not order.payment_ids._payment_order_todo()
            ):
                order.with_context(
                    payment_order_posted_by_jobs=True
                ).generated2uploaded()
        return True
