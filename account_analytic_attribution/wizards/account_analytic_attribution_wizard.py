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

    date_range_ids = fields.Many2many(
        'date.range', 'attribution_wizard_date_range_rel',
        string='Date range',
        domain=[('type_id.fiscal_month', '=', True)],
        help='Takes the current year if none is selected.', readonly=False
    )

    @api.multi
    def perform_distribution(self):
        """ Perform analytic attributions. """
        self.ensure_one()
        lines = self.env['account.analytic.line']
        for date_range in self.date_range_ids:
            lines += self.env[
                'account.analytic.attribution'].perform_distribution(
                date_range.date_start, date_range.date_end)

        return {
            'name': _('Generated Analytic Lines'),
            'view_mode': 'tree,form',
            'view_type': 'form',
            'res_model': 'account.analytic.line',
            'domain': [('id', 'in', lines.ids)],
            'context': {'group_by': ['ref']},
            'type': 'ir.actions.act_window',
        }
