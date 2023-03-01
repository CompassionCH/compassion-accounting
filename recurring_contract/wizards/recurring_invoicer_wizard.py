##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import calendar
from datetime import datetime

from odoo import fields, models, api


class InvoicerWizard(models.TransientModel):
    """ This wizard generate invoices from contract groups when launched.
    By default, all contract groups are used.
    """
    _name = 'recurring.invoicer.wizard'
    _description = 'Recurring invoicer wizard'

    generation_date = fields.Date(readonly=True)

    def generate(self):
        self.env.cr.execute(f"""
        SELECT DISTINCT gr.id 
        FROM recurring_contract rc
        JOIN recurring_contract_group gr ON rc.group_id = gr.id
        WHERE rc.state IN ('active', 'waiting')
        AND rc.total_amount > 0
        AND (rc.end_date IS NULL OR rc.end_date >= CURRENT_DATE + INTERVAL '1 month')
        AND NOT EXISTS(
            SELECT id
            FROM account_move_line aml
            WHERE contract_id = rc.id
            AND payment_state = 'not_paid'
            AND date_maturity >= CURRENT_DATE + (INTERVAL '1 month' * gr.advance_billing_months)
        )
        """)
        group_ids = [r[0] for r in self.env.cr.fetchall()]
        groups = self.env["recurring.contract.group"].browse(group_ids)

        # Add a job for all groups and start the job when all jobs are created.
        invoicer = groups.generate_invoices()
        res_id = False
        if invoicer:
            res_id = invoicer.id
        return {
            'name': 'recurring.invoicer.form',
            'view_mode': 'form',
            'res_id': res_id,  # id of the object to which to redirect
            'res_model': 'recurring.invoicer',  # object name
            'type': 'ir.actions.act_window',
        }

    @api.model
    def generate_from_cron(self):
        self.generate()
        return True
