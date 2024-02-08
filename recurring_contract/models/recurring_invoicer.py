##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

import logging

from odoo import _, fields, models

logger = logging.getLogger(__name__)


class RecurringInvoicer(models.Model):
    """An invoicer holds a bunch of invoices that have been generated
    in the same context. It also makes the validating or cancelling process
    of these contracts easy.
    """

    _name = "recurring.invoicer"
    _order = "generation_date desc"
    _description = "Recurring invoicer"

    generation_date = fields.Datetime(default=fields.Datetime.now)
    invoice_ids = fields.One2many(
        "account.move", "recurring_invoicer_id", "Generated invoices", readonly=False
    )

    def cancel_invoices(self):
        """
        Cancel created invoices (set state from open to cancelled)
        :return: True
        """
        invoice_to_cancel = self.mapped("invoice_ids").filtered(
            lambda invoice: invoice.state != "cancel"
        )
        invoice_to_cancel.button_draft()
        invoice_to_cancel.button_cancel()
        return True

    def show_invoices(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoices"),
            "view_mode": "tree,form",
            "views": [[False, "tree"], [False, "form"]],
            "res_model": "account.move",
            "domain": [("id", "in", self.invoice_ids.ids)],
            "target": "current",
            "context": self.env.context,
        }
