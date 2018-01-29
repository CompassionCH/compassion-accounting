# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from datetime import datetime

from odoo import api, fields, models, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF

import logging

logger = logging.getLogger(__name__)


class RecurringInvoicer(models.Model):
    ''' An invoicer holds a bunch of invoices that have been generated
    in the same context. It also makes the validating or cancelling process
    of these contracts easy.
    '''
    _name = 'recurring.invoicer'
    _rec_name = 'identifier'
    _order = 'generation_date desc'

    identifier = fields.Char(
        required=True, default=lambda self: self.calculate_id())
    source = fields.Char('Source model', required=True)
    generation_date = fields.Date(default=datetime.today().strftime(DF))
    invoice_ids = fields.One2many(
        'account.invoice', 'recurring_invoicer_id',
        'Generated invoices')

    def calculate_id(self):
        return self.env['ir.sequence'].next_by_code('rec.invoicer.ident')

    @api.multi
    def cancel_invoices(self):
        """
        Cancel created invoices (set state from open to cancelled)
        :return: True
        """
        invoice_to_cancel = self.mapped('invoice_ids').filtered(
            lambda invoice: invoice.state != 'cancel')

        invoice_to_cancel.action_invoice_cancel()

        return True

    @api.multi
    def show_invoices(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'views': [
                (self.env.ref('account.invoice_tree').id, 'tree'),
                (self.env.ref('account.invoice_form').id, 'form'),
            ],
            'res_model': 'account.invoice',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'target': 'current',
            'context': self.env.context,
        }
