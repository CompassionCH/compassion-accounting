# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    @author: Quentin Gigon <gigon.quentin@gmail.com>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import models, fields, api, _
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    move_bills_date = fields.Boolean(string="Move unclosed bills to next "
                                            "fiscal year", default=False)

    @api.multi
    def _validate_fiscalyear_lock(self, values):
        # res = super(ResCompany, self)._validate_fiscalyear_lock(values)
        if values.get('fiscalyear_lock_date'):
            nb_draft_entries = self.env['account.move'].search([
                ('company_id', 'in', [c.id for c in self]),
                ('state', 'in', ['draft', 'open']),
                ('date', '<=', values['fiscalyear_lock_date'])])

            config = self.env['account.config.settings'].search([
                ('company_id', '=', self.id)
            ], order="create_date desc", limit=1)

            if config.move_bills_date:
                for entry in nb_draft_entries:
                    # change date of billing to 1 day after last day of fiscal
                    # year
                    entry.sudo().write({'date': datetime.strptime(values.get(
                        'fiscalyear_lock_date'), '%Y-%m-%d').date()
                                                + timedelta(days=1)})
            else:
                raise ValidationError(_('There are still unposted entries in '
                                        'the period you want to lock. You '
                                        'should either post or delete them or '
                                        'push them to next fiscal year'))
