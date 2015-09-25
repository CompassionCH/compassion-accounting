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

from openerp import api, fields, models


class AccountStatement(models.Model):
    """ Adds a relation to a recurring invoicer. """

    _inherit = 'account.bank.statement'

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################

    recurring_invoicer_id = fields.Many2one(
        'recurring.invoicer', 'Invoicer')
    generated_invoices_count = fields.Integer('Invoices',
                                              compute='_count_invoices')

    ##########################################################################
    #                             FIELDS METHODS                             #
    ##########################################################################

    @api.one
    @api.depends('recurring_invoicer_id')
    def _count_invoices(self):
        self.generated_invoices_count = len(
            self.recurring_invoicer_id.invoice_ids)

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################

    @api.multi
    def to_invoices(self):
        self.ensure_one()
        return {
            'name': 'Generated Invoices',
            'view_mode': 'tree,form',
            'view_type': 'form',
            'res_model': 'account.invoice',
            'domain': [('recurring_invoicer_id', '=',
                        self.recurring_invoicer_id.id)],
            'type': 'ir.actions.act_window',
            'target': 'current',
            'context': {'form_view_ref': 'account.invoice_form',
                        'journal_type': 'sale'},
        }

    @api.multi
    def unlink(self):
        for statement in self:
            statement.recurring_invoicer_id.cancel_invoices()
        return super(AccountStatement, self).unlink()
