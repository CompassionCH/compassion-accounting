# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import fields, models


class AccountInvoice(models.Model):
    _name = 'account.invoice'
    _inherit = 'account.invoice'

    recurring_invoicer_id = fields.Many2one(
        'recurring.invoicer', 'Invoicer')


class AccountInvoiceLine(models.Model):
    _name = 'account.invoice.line'
    _inherit = 'account.invoice.line'

    contract_id = fields.Many2one(
        'recurring.contract', 'Source contract')

    due_date = fields.Date(
        related='invoice_id.date_due',
        readonly=True, store=True)

    state = fields.Selection(
        related='invoice_id.state',
        readonly=True, store=True)
