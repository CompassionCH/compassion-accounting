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
        curr_invoice_day = self._get_current_invoice_day()
        self.env.cr.execute(f"""
        SELECT DISTINCT id FROM recurring_contract
            WHERE invoice_day = '{curr_invoice_day}'
                AND (invoice_suspended_until IS null 
                    OR invoice_suspended_until <= CURRENT_DATE)
                AND state IN ('active', 'waiting')
                AND total_amount > 0
                AND (end_date is null OR end_date >= make_date(cast(date_part('year', CURRENT_DATE) as int), 
                                                               cast(date_part('month', CURRENT_DATE) as int), 
                                                           	   {curr_invoice_day}))
                AND id NOT IN (SELECT DISTINCT contract_id FROM account_move_line
                                    WHERE recurring_contract.id = contract_id
                                        AND move_id IN (SELECT DISTINCT id FROM account_move
                                                           WHERE payment_state = 'not_paid'
                                                              AND invoice_date >= CURRENT_DATE)
                                        );
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

    @api.model
    def _get_current_invoice_day(self):
        """
        Method that return the simulated day of the month for the query to retrieve the good data
        """
        today = datetime.now()
        last_day = calendar.monthrange(today.year, today.month)[1]
        if last_day <= today.day:
            return 31
        else:
            return today.day
