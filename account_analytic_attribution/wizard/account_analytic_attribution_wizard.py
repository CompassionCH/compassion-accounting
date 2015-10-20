# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from openerp import api, fields, models, exceptions, _


class account_analytic_attribution_wizard(models.TransientModel):
    """Wizard for performing attribution of analytic lines into
    other analytic accounts."""
    _name = 'account.analytic.attribution.wizard'

    period_id = fields.Many2one('account.period', 'Period')
    fiscalyear_id = fields.Many2one('account.fiscalyear', 'Fiscal year')

    @api.multi
    def perform_attribution(self):
        """ Perform analytic attributions. """
        periods = self._extract_periods()

        # Get the attribution analytic journal and root analytic account
        journal_id = self.env.ref(
            'account_analytic_attribution.journal_attribution').id
        attribution_analytic_id = self.env.ref(
            'account_analytic_attribution'
            '.account_analytic_root_to_attribute').id

        analytic_line_obj = self.env['account.analytic.line']
        analytic_default_obj = self.env['account.analytic.default']
        generated_lines = list()
        for period in periods:
            if period.state == 'closed':
                # Skip closed periods
                continue

            # Remove old attributions for avoiding duplicates
            old_lines = analytic_line_obj.search([
                ('journal_id', '=', journal_id),
                ('date', '>=', period.date_start),
                ('date', '<=', period.date_stop)])
            old_lines.unlink()

            # Perform the attribution for each analytic line below attribution
            # center (root analytic account)
            line_ids = analytic_line_obj.search([
                ('account_id', 'child_of', attribution_analytic_id),
                ('date', '>=', period.date_start),
                ('date', '<=', period.date_stop)]).ids

            generated_lines.extend(analytic_default_obj.perform_attribution(
                line_ids, journal_id, period.date_start, period.date_stop))

        return {
            'name': _('Generated Analytic Lines'),
            'view_mode': 'tree,form',
            'view_type': 'form',
            'res_model': 'account.analytic.line',
            'domain': [('id', 'in', generated_lines)],
            'context': {'group_by': ['ref', 'date']},
            'type': 'ir.actions.act_window',
        }

    @api.multi
    def transfer_moves_to_opening_period(self):
        """ Utility method to transfer open invoices moves into the next
        opening period before closing a period. This is useful for allowing
        cancelling the related invoices even after having closed the period.
        """
        periods = self._extract_periods()
        for period in periods:
            open_moves = self.env['account.invoice'].search([
                ('type', '=', 'out_invoice'),
                ('state', '=', 'open'),
                ('date_invoice', '>=', period.date_start),
                ('date_invoice', '<=', period.date_stop)]).mapped('move_id')
            next_opening_period = self.env['account.period'].search([
                ('state', '=', 'draft'),
                ('special', '=', True),
                ('date_start', '>', period.date_stop)], limit=1)
            open_moves.write({
                'period_id': next_opening_period.id,
                'date': next_opening_period.date_start})
        return True

    def _extract_periods(self):
        """ Get the relevant periods given the context. """
        self.ensure_one()
        periods = self.env['account.period']
        if self.env.context.get('active_model') == 'account.period':
            periods = self.env['account.period'].browse(
                self.env.context.get('active_ids'))
        fiscalyear = self.fiscalyear_id
        if fiscalyear:
            if fiscalyear.state == 'draft':
                periods = fiscalyear.period_ids
            elif fiscalyear.state == 'done':
                raise exceptions.Warning(
                    _("Fiscal Year closed"),
                    _("You cannot perform the computation on "
                      "closed fiscal year."))
        elif self.period_id:
            periods = self.period_id
        return periods
