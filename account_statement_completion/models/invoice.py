# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, models, fields


class AccountInvoice(models.Model):
    """ Adds two buttons for opening transactions of partner from invoice
    which eases the verification of generated invoices for the user."""

    _inherit = "account.invoice"

    unrec_items = fields.Integer(compute='_compute_unrec_items')

    @api.multi
    def _compute_unrec_items(self):
        move_line_obj = self.env['account.move.line']
        for invoice in self:
            partner = self.partner_id
            invoice.unrec_items = move_line_obj.search_count([
                ('partner_id', '=', partner.id),
                ('reconciled', '=', False),
                ('account_id.reconcile', '!=', False)])

    @api.multi
    def show_transactions(self):
        return self.partner_id.show_lines()

    @api.multi
    def show_move_lines(self):
        partner_id = self.partner_id.id
        action = {
            'name': 'Journal Items',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'res_model': 'account.move.line',
            'src_model': 'account.invoice',
            'context': {'search_default_partner_id': [partner_id],
                        'default_partner_id': partner_id,
                        'search_default_unreconciled': 1},
        }

        return action
