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

from openerp import api, models, fields


class account_invoice(models.Model):
    """ Adds two buttons for opening transactions of partner from invoice
    which eases the verification of generated invoices for the user."""

    _inherit = "account.invoice"

    unrec_items = fields.Integer(related='partner_id.unrec_items')

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
