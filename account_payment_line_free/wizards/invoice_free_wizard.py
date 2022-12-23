# -*- coding: utf-8 -*-
# Copyright 2020 Compassion Suisse (http://www.compassion.ch)
# @author: david wulliamoz, Emanuel Cino
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models, api


class AccountInvoiceFree(models.TransientModel):

    ''' Wizard to free invoices. When job is done, user is redirected on new
        payment order.
    '''
    _name = 'account.move.free'
    _description = 'Free invoice wizard'

    def invoice_free(self):
        inv_obj = self.env['account.move']
        invoices = inv_obj.browse(self.env.context.get('active_ids'))
        return invoices.free_payment_lines()
