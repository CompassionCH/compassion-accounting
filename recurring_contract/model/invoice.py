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
from openerp.tools.translate import _


class account_invoice(models.Model):
    _name = 'account.invoice'
    _inherit = 'account.invoice'

    recurring_invoicer_id = fields.Many2one(
        'recurring.invoicer', _('Invoicer'))


class account_invoice_line(models.Model):
    _name = 'account.invoice.line'
    _inherit = 'account.invoice.line'

    def _get_dates(self):
        res = {}
        for line in self:
            res[line.id] = line.invoice_id.date_due or False

        return res

    def _get_states(self):
        res = {}
        for line in self:
            res[line.id] = line.invoice_id.state

        return res

    @api.depends('invoice_id.state')
    def _get_invoice_lines_state(self):
        for invoice_line in self:
            invoice_line.state = invoice_line.invoice_id.state

    @api.depends('due_date')
    def _get_invoice_lines_date_due(self):
        for invoice_line in self:
            invoice_line.due_date = invoice_line.invoice_id.date_due

    contract_id = fields.Many2one(
        'recurring.contract', _('Source contract'))

    due_date = fields.Date(
        compute='_get_invoice_lines_date_due', string=_('Due date'),
        readonly=True, strore=True)

    state = fields.Selection(
        compute='_get_invoice_lines_state', string=_('State'),
        readonly=True, strore=True,
        selection=[('draft', 'Draft'),
                   ('proforma', 'Pro-forma'),
                   ('proforma2', 'Pro-forma'),
                   ('open', 'Open'),
                   ('paid', 'Paid'),
                   ('cancel', 'Cancelled')])
