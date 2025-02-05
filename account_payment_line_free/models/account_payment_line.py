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
        default=False,
        help="This field indicates if the invoice is still "
        "linked with the payment line",
    )

    def free_line(self, rsn=""):
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
            invoice = payment_line.move_line_id.move_id
            order = payment_line.order_id

            render_values_invoice = {
                "invoice": invoice,
                "order": order,
                "additional_msg": additional_msg or "",
            }

            render_values_payment_order = {
                "invoice": invoice,
                "payment_line_name": payment_line.name,
                "additional_msg": additional_msg or "",
            }

            # Post message on invoice (linking to payment order)
            invoice.message_post_with_source(
                "account_payment_line_free.message_payment_line_unlinked",
                render_values=render_values_invoice,
                subtype_xmlid="mail.mt_note",
            )

            # Post message on payment order (linking to invoice)
            order.message_post_with_source(
                "account_payment_line_free.message_payment_order_unlinked",
                render_values=render_values_payment_order,
                subtype_xmlid="mail.mt_note",
            )
