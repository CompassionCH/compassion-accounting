# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, models, fields, _


class AttributionWizard(models.TransientModel):
    """Wizard for performing attribution of analytic lines into
    other analytic accounts."""
    _name = 'account.analytic.attribution.wizard'

    date_range_id = fields.Many2one(
        'date.range', 'Date range',
        help='Takes the current year if none is selected.')
    date_start = fields.Date(related='date_range_id.date_start')
    date_stop = fields.Date(related='date_range_id.date_end')

    @api.multi
    def perform_distribution(self):
        """ Perform analytic attributions. """
        self.ensure_one()
        lines = self.env[
            'account.analytic.attribution'].perform_distribution(
            self.date_start, self.date_stop)

        return {
            'name': _('Generated Analytic Lines'),
            'view_mode': 'tree,form',
            'view_type': 'form',
            'res_model': 'account.analytic.line',
            'domain': [('id', 'in', lines.ids)],
            'context': {'group_by': ['ref']},
            'type': 'ir.actions.act_window',
        }
