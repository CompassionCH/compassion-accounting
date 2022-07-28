##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import fields, models, api

class InvoicerWizard(models.TransientModel):
    ''' This wizard generate invoices from contract groups when launched.
    By default, all contract groups are used.
    '''
    _name = 'recurring.invoicer.wizard'
    _description = 'Recurring invoicer wizard'

    generation_date = fields.Date(readonly=True)

    def generate(self):

        recurring_invoicer_obj = self.env['recurring.invoicer']

        self.env.cr.execute("""
        SELECT DISTINCT group_id FROM recurring_contract
        WHERE
            next_invoice_date IS NOT NULL AND
            next_invoice_date <= now() + interval '1 month'
            AND state NOT IN ('terminated', 'cancelled', 'draft')
            AND total_amount > 0;
        """)
        gids = [r[0] for r in self.env.cr.fetchall()]
        contract_groups = self.env["recurring.contract.group"].browse(gids)

        invoicer = recurring_invoicer_obj.create({})
        # Add a job for all groups and start the job when all jobs are created.
        for group in contract_groups:
            group.generate_invoices(invoicer)

        return {
            'name': 'recurring.invoicer.form',
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': invoicer.id,  # id of the object to which to redirect
            'res_model': 'recurring.invoicer',  # object name
            'type': 'ir.actions.act_window',
        }

    @api.model
    def generate_from_cron(self):
        self.generate()
        return True
