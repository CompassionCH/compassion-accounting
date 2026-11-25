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
            draft_payments = order.payment_ids.filtered(lambda p: p.state == "draft")
            draft_payments.with_delay_sh(
                "payment_order_post_and_reconcile",
                split=PAYMENTS_PER_JOB,
                chain=True,
                description=f"Post and reconcile payments of {order.name}",
            )
            order.message_post(
                body=self.env._(
                    "%(count)s payments are being posted in background jobs. "
                    "The order will be set to uploaded once they are all posted.",
                    count=len(draft_payments),
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

    def payment_order_post_and_reconcile(self):
        """Job method: same as account.payment.order.post_and_reconcile, for
        a chunk of payments. The last chunk sets the order to uploaded."""
        for payment in self.filtered(lambda p: p.state == "draft"):
            payment.action_post()
            (
                payment.payment_line_ids.move_line_id
                + payment.move_id.line_ids.filtered(
                    lambda x, p=payment: x.account_id == p.destination_account_id
                )
            ).reconcile()
        for order in self.payment_order_id:
            if order.state == "generated" and not order.payment_ids.filtered(
                lambda p: p.state == "draft"
            ):
                order.with_context(
                    payment_order_posted_by_jobs=True
                ).generated2uploaded()
        return True
