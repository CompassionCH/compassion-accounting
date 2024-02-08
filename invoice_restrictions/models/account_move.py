##############################################################################
#
#    Copyright (C) 2014-2023 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = "account.move"

    def write(self, vals):
        is_write_paystate = vals.get("payment_state")

        # We don't want to take the move out of the payment order in case
        # it's getting paid
        if not is_write_paystate:
            move_to_modify = self.filtered("line_ids.payment_line_ids")
            if move_to_modify:
                move_to_modify.with_context("unlink_line").free_payment_lines()
        res = super().write(vals)
        # Refresh the browser to be sure the user see the message posted
        if move_to_modify:
            # We read the payment to the order
            if not is_write_paystate:
                move_to_modify.create_account_payment_line()
            return {
                "type": "ir.actions.client",
                "tag": "reload",
            }
        return res
