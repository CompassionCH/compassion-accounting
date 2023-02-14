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
        SELECT DISTINCT recurring_contract.id 
        FROM recurring_contract
        INNER JOIN account_move_line ON recurring_contract.id = account_move_line.contract_id
        INNER JOIN account_move ON account_move_line.move_id = account_move.id
        WHERE recurring_contract.state IN ('active', 'waiting')
            AND total_amount > 0
            AND (end_date IS NULL OR end_date >= CURRENT_DATE + INTERVAL '1 month')
            AND account_move.payment_state = 'not_paid'
            AND account_move.invoice_date < CURRENT_DATE + INTERVAL '1 month'
        """)
        contract_ids = [r[0] for r in self.env.cr.fetchall()]
        contracts = self.env["recurring.contract"].browse(contract_ids)

        # Add a job for all groups and start the job when all jobs are created.
        invoicer = contracts.generate_invoices()
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
