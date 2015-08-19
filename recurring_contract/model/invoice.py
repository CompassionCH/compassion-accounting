# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from openerp import api, fields, models


class account_invoice(models.Model):
    _name = 'account.invoice'
    _inherit = 'account.invoice'

    recurring_invoicer_id = fields.Many2one(
        'recurring.invoicer', 'Invoicer')


class account_invoice_line(models.Model):
    _name = 'account.invoice.line'
    _inherit = 'account.invoice.line'

    contract_id = fields.Many2one(
        'recurring.contract', 'Source contract')

    due_date = fields.Date(
        compute='_get_invoice_lines_date_due',
        readonly=True, store=True)

    state = fields.Selection(
        compute='_get_invoice_lines_state',
        readonly=True, store=True,
        selection=[('draft', 'Draft'),
                   ('proforma', 'Pro-forma'),
                   ('proforma2', 'Pro-forma'),
                   ('open', 'Open'),
                   ('paid', 'Paid'),
                   ('cancel', 'Cancelled')])

    @api.depends('invoice_id.state')
    def _get_invoice_lines_state(self):
        for invoice_line in self:
            invoice_line.state = invoice_line.invoice_id.state

    @api.depends('invoice_id.date_due')
    def _get_invoice_lines_date_due(self):
        for invoice_line in self:
            invoice_line.due_date = invoice_line.invoice_id.date_due
