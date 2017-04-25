# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from openerp import api, models, _


class AttributionWizard(models.TransientModel):
    """Wizard for performing attribution of analytic lines into
    other analytic accounts."""
    _name = 'account.analytic.attribution.wizard'

    @api.multi
    def perform_distribution(self):
        """ Perform analytic attributions. """
        lines = self.env[
            'account.analytic.attribution'].perform_distribution(manual=True)

        return {
            'name': _('Generated Analytic Lines'),
            'view_mode': 'tree,form',
            'view_type': 'form',
            'res_model': 'account.analytic.line',
            'domain': [('id', 'in', lines.ids)],
            'context': {'group_by': ['ref']},
            'type': 'ir.actions.act_window',
        }
