##############################################################################
#
#    Copyright (C) 2014-2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: David Wulliamoz, Emmanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import _, exceptions, fields, models


class AccountPaymentLine(models.Model):
    _inherit = "account.payment.line"

    returned = fields.Boolean(
        string="Move unlinked",
        readonly=True,
        default=False,
        help="This field indicates if the invoice is still "
        "linked with the payment line",
    )

    def free_line(self, rsn=""):
        """
        Set move_line_id to Null in order to cancel the related invoice
        check if the payment_line is returned, if not, check the related
        move_line is not reconciled
        """
        for rec in self:
            if "paid" not in rec.payment_ids.reconciled_invoice_ids.mapped(
                "payment_state"
            ):
                rec._post_free_message(str(rsn))
                if self.env.context.get("unlink_line", False):
                    rec.unlink()
                else:
                    rec.move_line_id = False
                    rec.returned = True
                    rec.payment_ids.action_draft()
                    rec.payment_ids.action_cancel()
            else:
                raise exceptions.UserError(
                    _("Payment is reconciled and cannot be cancelled.")
                )

    def _post_free_message(self, additional_msg=""):
        """
        post message on the invoice that have been freed from the payment order
        post message on the payment order for each payment_line unlinked
        from the move_line.
        """
        for payment_line in self:
            # Create a link to the invoice that was removed
            invoice = payment_line.move_line_id.move_id
            order = payment_line.order_id
            if additional_msg != "":
                additional_msg = "\n" + additional_msg
            invoice_url = (
                f'<a href="web#id={invoice.id}&view_type=form&model='
                f'account.move">{invoice.name}</a>'
            )
            payment_order_url = (
                f'<a href="web#id={order.id}&view_type=form&model='
                f'account.payment.order">{order.name}</a>'
            )
            # Add a message to the invoice
            invoice.message_post(
                body="The invoice has been marked as returned and freed from "
                + payment_order_url
                + additional_msg
            )
            # Add a message to the payment order
            payment_line.order_id.message_post(
                body=invoice_url
                + " has been unlinked from the line: "
                + payment_line.name
                + additional_msg
            )
