##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, fields, models


class InvoicerWizard(models.TransientModel):
    """This wizard generate invoices from contract groups when launched.
    By default, all contract groups are used.
    """

    _name = "recurring.invoicer.wizard"
    _description = "Recurring invoicer wizard"

    generation_date = fields.Date(readonly=True)

    def generate(self):
        groups = self.env["recurring.contract.group"].search([
            "|", ("invoice_suspended_until", "=", False),
            ("invoice_suspended_until", "<", fields.Date.today()),
            ("has_active_contracts", "=", True),
        ])

        # Add a job for all groups and start the job when all jobs are created.
        invoicer = groups.generate_invoices()
        res_id = False
        if invoicer:
            res_id = invoicer.id
        return {
            "name": "recurring.invoicer.form",
            "view_mode": "form",
            "res_id": res_id,  # id of the object to which to redirect
            "res_model": "recurring.invoicer",  # object name
            "type": "ir.actions.act_window",
        }

    @api.model
    def generate_from_cron(self):
        self.generate()
        return True
