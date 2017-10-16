# -*- encoding: utf-8 -*-
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
    def next_fiscal_year(self):
        today = datetime.today()
        fy = self.env.user.company_id.compute_fiscalyear_dates(today)
        next_fy = fy['date_to'] + relativedelta(days=1)
        next_fy.hour = 20
        return fields.Datetime.to_string(next_fy)

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
    def perform_distribution(self, manual=False):
        """
        Perform the attribution of the analytic lines.
        The attribution is done for each general account.
        By default it takes the last fiscal year for the computation.
        If manual is set to true, the computation will be made for the
        current fiscal year.
        """
        # Select the period
        year = datetime.today()
        if not manual:
            year = year - relativedelta(years=1)
        fy = self.env.user.company_id.compute_fiscalyear_dates(year)
        date_start = fields.Date.to_string(fy['date_from'])
        date_stop = fields.Date.to_string(fy['date_to'])

        analytic_line_obj = self.env['account.analytic.line']
        tag_id = self.env.ref(
            'account_analytic_attribution.tag_attribution').id

        # Remove old attributions for avoiding duplicates
        old_lines = analytic_line_obj.search([
            ('tag_ids', '=', tag_id),
            ('date', '>=', date_start),
            ('date', '<=', date_stop)])
        old_lines.unlink()

        # Perform the attribution for each analytic line
        analytic_lines = analytic_line_obj.search([
            ('date', '>=', date_start),
            ('date', '<=', date_stop),
        ])
        generated_lines = analytic_line_obj

        # Get the total amount to attribute for each analytic account
        #   ->   {analytic_id: {general_account_id: total}}
        attribution_amounts = dict()
        for line in analytic_lines:
            analytic_id = line.account_id.id
            account_id = line.general_account_id.id
            analytic_attribution = attribution_amounts.get(analytic_id, {
                account_id: 0.0})
            total = analytic_attribution.get(account_id, 0.0) + line.amount
            analytic_attribution[account_id] = total
            attribution_amounts[analytic_id] = analytic_attribution

        # Attribute the amounts
        for analytic_id, attribution in attribution_amounts.iteritems():
            for account_id, amount_total in attribution.iteritems():
                attribution_rule = self.get_attribution(
                    line.general_account_id.tag_ids.ids,
                    line.account_id.tag_ids.ids,
                    line.date
                )
                if attribution_rule:
                    analytic_account = self.env[
                        'account.analytic.account'].browse(analytic_id)
                    prefix = (analytic_account.code and
                              analytic_account.code + '-') or ''
                    for rule in attribution_rule.account_distribution_line_ids:
                        line = analytic_line_obj.create({
                            'name': 'Analytic attribution for ' +
                                    analytic_account.name,
                            'account_id': rule.account_analytic_id.id,
                            'date': date_stop,
                            'tag_ids': [(6, 0, [tag_id])],
                            'amount': amount_total * (rule.rate / 100),
                            'general_account_id': account_id,
                            'ref': prefix + analytic_account.name,
                        })
                        generated_lines += line

        return generated_lines
