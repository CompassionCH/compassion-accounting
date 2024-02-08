##############################################################################
#
#    Copyright (C) 2014-2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: David Wulliamoz, Emmanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import _, exceptions, models


class AccountMove(models.Model):
    """add invoice freeing functionality."""

    _inherit = "account.move"

    def free_payment_lines(self):
        """finds related payment lines and free them."""
        for record in self:
            # We perform a search because some invoices may be not well
            # linked with their lines
            move_line_ids = (
                self.env["account.move.line"].search([("move_id", "=", record.id)]).ids
            )
            payment_lines = self.env["account.payment.line"].search(
                [("move_line_id", "in", move_line_ids)]
            )
            if not payment_lines:
                raise exceptions.UserError(_("No payment line found !"))

            payment_lines.free_line()
        if self.ids:
            return {
                "name": _("Freed invoices"),
                "type": "ir.actions.act_window",
                "view_mode": "tree,form",
                "res_model": "account.move",
                "domain": [("id", "in", self.ids)],
                "target": "current",
            }
        else:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No invoice(s) unlinked"),
                    "message": "No invoices where find to be unlinked from "
                    "payment order.",
                    "sticky": False,
                },
            }
