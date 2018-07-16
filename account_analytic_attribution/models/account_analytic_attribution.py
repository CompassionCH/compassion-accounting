# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from datetime import datetime

from odoo.tools import relativedelta

from odoo import api, models, fields


class AccountAttribution(models.Model):
    """
    Attribution are used for dispatching analytic lines into other analytic
    accounts.
    """
    _name = "account.analytic.attribution"
    _description = "Analytic Attribution"
    _order = "sequence desc"

    account_tag_id = fields.Many2one(
        'account.account.tag', 'Account Tag', ondelete='cascade'
    )
    analytic_tag_id = fields.Many2one(
        'account.analytic.tag', 'Analytic Tag',
        ondelete='cascade'
    )
    account_distribution_line_ids = fields.One2many(
        'account.analytic.distribution.line', 'attribution_id', 'Distribution',
        required=True
    )
    date_start = fields.Date()
    date_stop = fields.Date()
    sequence = fields.Integer()
    next_fiscal_year = fields.Date(compute='_compute_next_fy')

    @api.model
    def get_attribution(self, account_tag_ids, analytic_tag_ids, date):
        """ Find a valid distribution rule given some data. """
        domain = [
            '|', ('date_start', '<=', date), ('date_start', '=', False),
            '|', ('date_stop', '>=', date), ('date_stop', '=', False)
        ]
        if account_tag_ids:
            domain += ['|', ('account_tag_id', 'in', account_tag_ids),
                       ('account_tag_id', '=', False)]

        if analytic_tag_ids:
            domain += ['|', ('analytic_tag_id', 'in', analytic_tag_ids),
                       ('analytic_tag_id', '=', False)]

        return self.search(domain, limit=1)

    @api.model
    def perform_distribution(self, date_start=None, date_stop=None):
        """
        Perform the attribution of the analytic lines.
        The attribution is done for each general account.
        By default it takes the last fiscal year for the computation.
        """
        date_start, date_stop = self._compute_dates(date_start, date_stop)
        analytic_line_obj = self.env['account.analytic.line']
        tag_id = self.env.ref(
            'account_analytic_attribution.tag_attribution').id

        analytic_lines = self._filter_analytic_lines_and_removed_old_ones(
            date_start, date_stop, tag_id)
        generated_lines = analytic_line_obj

        attribution_amounts = self._aggregate_by_account(analytic_lines)

        # Attribute the amounts
        analytic_account_obj = self.env['account.analytic.account']
        account_obj = self.env['account.account']
        for analytic_id, attribution in attribution_amounts.iteritems():
            for account_id, amount_total in attribution.iteritems():
                account = account_obj.browse(account_id)
                account_tag_ids = account.tag_ids.ids
                analytic = analytic_account_obj.browse(analytic_id)
                analytic_tag_ids = analytic.tag_ids.ids
                attribution_rule = self.get_attribution(
                    account_tag_ids, analytic_tag_ids, date_stop)
                if attribution_rule:
                    prefix = (analytic.code and
                              analytic.code + '-') or ''
                    for rule in attribution_rule.account_distribution_line_ids:
                        line = analytic_line_obj.create({
                            'name': 'Analytic attribution for ' +
                                    analytic.name,
                            'account_id': rule.account_analytic_id.id,
                            'date': date_stop,
                            'tag_ids': [(6, 0, [tag_id])],
                            'amount': amount_total * (rule.rate / 100),
                            'general_account_id': account_id,
                            'ref': prefix + analytic.name,
                        })
                        generated_lines += line

        return generated_lines

    def _compute_dates(self, date_start=None, date_stop=None):
        if not date_start or not date_stop:
            # Select the last year period
            year = datetime.today()
            year = year - relativedelta(years=1)
            fy = self.env.user.company_id.compute_fiscalyear_dates(year)
            date_start = fields.Date.to_string(fy['date_from'])
            date_stop = fields.Date.to_string(fy['date_to'])
        return date_start, date_stop

    def _filter_analytic_lines_and_removed_old_ones(self, date_start,
                                                    date_stop, tag_id):
        analytic_line_obj = self.env['account.analytic.line']
        # Remove old attributions for avoiding duplicates
        old_lines = analytic_line_obj.search([
            ('tag_ids', '=', tag_id),
            ('date', '>=', date_start),
            ('date', '<=', date_stop)])
        old_lines.unlink()

        # Perform the attribution for each analytic line
        return analytic_line_obj.search([
            ('date', '>=', date_start),
            ('date', '<=', date_stop),
        ])

    @staticmethod
    def _aggregate_by_account(analytic_lines):
        """
        # Get the total amount to attribute for each analytic account
        #   ->   {analytic_id: {general_account_id: total}}
        """
        attribution_amounts = dict()
        for line in analytic_lines:
            analytic_id = line.account_id.id
            account_id = line.general_account_id.id
            analytic_attribution = attribution_amounts.get(analytic_id, {
                account_id: 0.0})
            total = analytic_attribution.get(account_id, 0.0) + line.amount
            analytic_attribution[account_id] = total
            attribution_amounts[analytic_id] = analytic_attribution
        return attribution_amounts
