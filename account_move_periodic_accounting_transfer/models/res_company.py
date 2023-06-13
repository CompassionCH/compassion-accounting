##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    @author: Quentin Gigon <gigon.quentin@gmail.com>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from datetime import timedelta

from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    move_bills_date = fields.Boolean(
        string="Move unclosed bills to next fiscal year"
    )

    def _validate_fiscalyear_lock(self, values):
        super()._validate_fiscalyear_lock(values)
        # Move open customer invoice open moves to next fiscal year
        lock_date = values.get('fiscalyear_lock_date')
        if lock_date:
            for company in self:
                if company.move_bills_date:
                    open_invoices = self.env['account.move'].search([
                        ('state', '=', 'posted'),
                        ('payment_state', '=', 'not_paid'),
                        ('move_type', '=', 'out_invoice'),
                        ('date', '<=', lock_date),
                        ('company_id', '=', self.env.company.id)
                    ])
                    first_day_in_next_fy = lock_date + timedelta(days=1)
                    moves = open_invoices.sudo()
                    for move in moves:
                        move.button_draft()
                        move.write({
                            'date': first_day_in_next_fy
                        })
                        move.action_post()
