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
        self.env.cr.execute(
            """
           SELECT gr.id
FROM recurring_contract_group gr
WHERE (gr.invoice_suspended_until IS NULL OR gr.invoice_suspended_until < CURRENT_DATE)
  AND EXISTS (
    SELECT 1
    FROM recurring_contract rc
    WHERE rc.group_id = gr.id
      AND rc.state IN ('active', 'waiting')
      AND rc.total_amount > 0
      AND (rc.end_date IS NULL OR rc.end_date >= CURRENT_DATE + INTERVAL '1 month')
      AND NOT EXISTS (
        SELECT 1
        FROM account_move_line aml
        JOIN account_move am ON aml.move_id = am.id
        WHERE aml.contract_id = rc.id
          AND am.state IN ('posted', 'cancel')
          AND am.invoice_date >= date_trunc('month', CURRENT_DATE + (INTERVAL '1 month' * gr.advance_billing_months))
      )
  );
        """
        )
        group_ids = [r[0] for r in self.env.cr.fetchall()]
        groups = self.env["recurring.contract.group"].browse(group_ids)

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
