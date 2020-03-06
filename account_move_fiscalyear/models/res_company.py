##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    @author: Quentin Gigon <gigon.quentin@gmail.com>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import models, fields, api
from datetime import timedelta


class ResCompany(models.Model):
    _inherit = 'res.company'

    move_bills_date = fields.Boolean(string="Move unclosed bills to next "
                                            "fiscal year", default=False)

    @api.multi
    def _validate_fiscalyear_lock(self, values):
        super()._validate_fiscalyear_lock(values)
        # Move open customer invoice open moves to next fiscal year
        lock_date = values.get('fiscalyear_lock_date')
        if lock_date:
            config = self.env['account.config.settings'].search([
                ('company_id', 'in', self.ids)
            ], order="create_date desc", limit=1)
            if config.move_bills_date:

                open_invoices = self.env['account.invoice'].search([
                    ('state', '=', 'open'),
                    ('type', '=', 'out_invoice'),
                    ('date_invoice', '<=', lock_date)
                ])
                first_day_in_next_fy = lock_date + timedelta(days=1)
                moves = open_invoices.mapped('move_id').sudo()
                moves.write({
                    'date': first_day_in_next_fy

                })
                analytic_lines = moves.mapped('line_ids.analytic_line_ids')
                analytic_lines.write({'date': first_day_in_next_fy})
