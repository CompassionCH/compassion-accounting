# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from openerp.osv import orm, fields
from openerp.tools.translate import _


class account_analytic_attribution_wizard(orm.TransientModel):
    """Wizard for performing attribution of analytic lines into
    other analytic accounts."""
    _name = 'account.analytic.attribution.wizard'

    _columns = {
        'period_id': fields.many2one(
            'account.period', _('Period')),
        'fiscalyear_id': fields.many2one(
            'account.fiscalyear', _('Fiscal year'))
    }

    def perform_attribution(self, cr, uid, ids, context=None):
        """ Perform analytic attributions. """
        if isinstance(ids, list):
            # Only one wizard at a time
            ids = ids[0]
        wizard = self.browse(cr, uid, ids, context)
        periods = list()
        if context.get('active_model') == 'account.period':
            periods = self.pool.get('account.period').browse(
                cr, uid, context.get('active_ids'), context)
        fiscalyear = wizard.fiscalyear_id
        if fiscalyear:
            if fiscalyear.state == 'draft':
                periods = fiscalyear.period_ids
            elif fiscalyear.state == 'done':
                raise orm.except_orm(
                    _("Fiscal Year closed"),
                    _("You cannot perform the computation on "
                      "closed fiscal year."))
        elif wizard.period_id:
            periods = [wizard.period_id]

        # Get the attribution analytic journal and root analytic account
        data_obj = self.pool.get('ir.model.data')
        journal_id = data_obj.get_object_reference(
            cr, uid, 'account_analytic_attribution',
            'journal_attribution')[1]
        attribution_analytic_id = data_obj.get_object_reference(
            cr, uid, 'account_analytic_attribution',
            'account_analytic_root_to_attribute')[1]

        analytic_line_obj = self.pool.get('account.analytic.line')
        analytic_default_obj = self.pool.get('account.analytic.default')
        generated_lines = list()
        for period in periods:
            if period.state == 'closed':
                # Skip closed periods
                continue

            # Remove old attributions for avoiding duplicates
            old_line_ids = analytic_line_obj.search(cr, uid, [
                ('journal_id', '=', journal_id),
                ('date', '>=', period.date_start),
                ('date', '<=', period.date_stop)], context=context)
            analytic_line_obj.unlink(cr, uid, old_line_ids, context)

            # Perform the attribution for each analytic line below attribution
            # center (root analytic account)
            line_ids = analytic_line_obj.search(cr, uid, [
                ('account_id', 'child_of', attribution_analytic_id),
                ('date', '>=', period.date_start),
                ('date', '<=', period.date_stop)], context=context)

            generated_lines.extend(analytic_default_obj.perform_attribution(
                cr, uid, line_ids, journal_id, period.date_start,
                period.date_stop, context))

        return {
            'name': _('Generated Analytic Lines'),
            'view_mode': 'tree,form',
            'view_type': 'form',
            'res_model': 'account.analytic.line',
            'domain': [('id', 'in', generated_lines)],
            'context': {'group_by': ['ref', 'date']},
            'type': 'ir.actions.act_window',
        }
