# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################
from openerp.osv import orm, fields
from openerp.tools.translate import _


class account_analytic_default(orm.Model):
    """ Adds a type of account_analytic_default for doing an attribution of an
    analytic account. """
    _inherit = "account.analytic.default"

    _columns = {
        'type': fields.selection([
            ('default', _('Default')),
            ('attribution', _('Attribution rule'))], _("Type")),
        'account_id': fields.many2one(
            'account.account', _("General Account")),
    }

    _defaults = {
        'type': 'default'
    }

    def account_get(self, cr, uid, product_id=None, partner_id=None,
                    user_id=None, date=None, company_id=None, context=None):
        """ Rewrite method to return only normal type of defaults. """
        return self._get_default(
            cr, uid, 'default', product_id, partner_id, user_id, date,
            company_id, context)

    def get_attribution(self, cr, uid, analytic_id=None, account_id=None,
                        date=None, context=None):
        """ Find a valid attribution rule given some data. """
        return self._get_default(
            cr, uid, 'attribution',  date=date, analytic_id=analytic_id,
            account_id=account_id, context=context)

    def perform_attribution(self, cr, uid, line_ids, journal_id, date_start,
                            date_stop, context=None):
        """ Perform the attribution of the analytic lines.
            The attribution is done for each general account. """
        analytic_line_obj = self.pool.get('account.analytic.line')
        generated_lines = list()

        # Get the total amount to attribute for each analytic account
        #   ->   {analytic_id: {general_account_id: total}}
        attribution_amounts = dict()
        for line in analytic_line_obj.browse(cr, uid, line_ids, context):
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
                    cr, uid, analytic_id, account_id, date_stop, context)
                if attribution_rule:
                    analytic_account = self.pool.get(
                        'account.analytic.account').browse(
                        cr, uid, analytic_id, context)
                    distribution = attribution_rule.analytics_id
                    for rule in distribution.account_ids:
                        line_id = analytic_line_obj.create(cr, uid, {
                            'name': 'Analytic attribution for ' +
                            analytic_account.name,
                            'account_id': rule.analytic_account_id.id,
                            'date': date_stop,
                            'journal_id': journal_id,
                            'amount': amount_total * (rule.rate / 100),
                            'general_account_id': account_id,
                            'ref': analytic_account.code + '-' +
                            analytic_account.name,
                            }, context)
                        generated_lines.append(line_id)

        return generated_lines

    def install(self, cr, uid):
        """ Sets the type of analytic defaults. """
        cr.execute("""
        UPDATE account_analytic_default SET type='default'
        WHERE type IS NULL""")

    def _get_default(self, cr, uid, type, product_id=None, partner_id=None,
                     user_id=None, date=None, analytic_id=None,
                     account_id=None, context=None):
        domain = [('type', '=', type)]
        if product_id:
            domain += ['|', ('product_id', '=', product_id)]
        domain += [('product_id', '=', False)]
        if partner_id:
            domain += ['|', ('partner_id', '=', partner_id)]
        domain += [('partner_id', '=', False)]
        if user_id:
            domain += ['|', ('user_id', '=', user_id)]
        domain += [('user_id', '=', False)]
        if date:
            domain += ['|', ('date_start', '<=', date),
                       ('date_start', '=', False)]
            domain += ['|', ('date_stop', '>=', date),
                       ('date_stop', '=', False)]

        for rec in self.browse(cr, uid, self.search(cr, uid, domain,
                                                    context=context),
                               context=context):
            if analytic_id and rec.analytic_id:
                children_analytic_ids = self.pool.get(
                    'account.analytic.account').search(
                        cr, uid, [('id', 'child_of', rec.analytic_id.id)],
                        context=context)
                if analytic_id not in children_analytic_ids:
                    continue

            if account_id and rec.account_id:
                children_account_ids = self.pool.get(
                    'account.account').search(
                        cr, uid, [('id', 'child_of', rec.account_id.id)],
                        context=context)
                if account_id not in children_account_ids:
                    continue
            return rec

        return False
