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
        # ruff: noqa: E501
        self.env.cr.execute(
            """
            -- Select distinct contract group IDs that are ready for invoicing.
            SELECT DISTINCT gr.id
            FROM recurring_contract rc
                     JOIN recurring_contract_group gr ON rc.group_id = gr.id
            WHERE
                rc.state IN ('active', 'waiting')
              AND rc.total_amount > 0
              AND (rc.end_date IS NULL OR rc.end_date >= date_trunc('month', CURRENT_DATE))
              AND (gr.invoice_suspended_until IS NULL OR gr.invoice_suspended_until < CURRENT_DATE)
              -- Check if there is any scheduled billing date within the advance period that is missing an invoice.
              AND EXISTS (
                -- Generate a series of future billing dates based on the group's specific recurrence settings.
                -- The series starts from the beginning of the current month.
                -- It extends for the number of months specified in 'advance_billing_months'.
                -- The step of the series is dynamic, based on the group's 'recurring_value' and 'recurring_unit'.
                SELECT 1
                FROM generate_series(
                         date_trunc('month', CURRENT_DATE),
                         date_trunc('month', CURRENT_DATE) + (INTERVAL '1 month' * (gr.advance_billing_months - 1)),
                         -- The interval is calculated dynamically for each group.
                         -- e.g., if recurring_value=3 and recurring_unit='month', the interval is '3 months'.
                         -- e.g., if recurring_value=1 and recurring_unit='year', the interval is '1 year'.
                         gr.recurring_value * CASE
                                                  WHEN gr.recurring_unit = 'year' THEN INTERVAL '1 year'
                                                  ELSE INTERVAL '1 month'
                             END
                     ) AS s(billing_date)
                -- For each generated billing date, check that no corresponding posted invoice exists for the partner.
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM account_move am
                             JOIN account_move_line aml ON aml.move_id = am.id
                    WHERE
                        aml.contract_id = rc.id
                      -- The invoice date must fall within the month of the generated billing date.
                      AND am.invoice_date >= s.billing_date
                      AND am.invoice_date < s.billing_date + INTERVAL '1 month'
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
