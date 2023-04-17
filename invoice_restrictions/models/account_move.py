##############################################################################
#
#    Copyright (C) 2014-2023 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models, _


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = 'account.move'

    def write(self, vals):
        # We don't want to take the move out of the payment order in case it's getting paid
        if not vals.get("payment_state"):
            move_to_modify = self.filtered('line_ids.payment_line_ids')
            if move_to_modify:
                payment_line_ids = move_to_modify.mapped('line_ids.payment_line_ids')
                pay_order = payment_line_ids.mapped('order_id')[0]
                # Use the limitation on the payment_line
                payment_line_ids.unlink()
                # Warn the user that it was taken out of the payment_order
                move_to_modify.message_post(
                    body=_(
                        "Payment line removed of the payment order "
                        "<a href=# data-oe-model=account.payment.order "
                        "data-oe-id=%d>%s</a>."
                    ) % (pay_order.id, pay_order.display_name)
                )
        res = super().write(vals)

        # Refresh the browser to be sure the user see the message posted
        if move_to_modify:
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        return res
