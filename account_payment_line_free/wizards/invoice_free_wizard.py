# -*- coding: utf-8 -*-
# Copyright 2020 Compassion Suisse (http://www.compassion.ch)
# @author: david wulliamoz, Emanuel Cino
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models, api
from odoo.exceptions import UserError


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

    def invoice_free_from_payment_order(self):
        # Retrieve all payment line that hasn't been paid
        inv_list = []
        payment_orders = self.env["account.payment.order"].browse(self.env.context.get("active_ids"))
        for pay_ord in payment_orders:
            for line in pay_ord.payment_line_ids:
                if line.move_line_id.payment_state != 'paid'\
                        and line.move_line_id:
                    inv_list.append(line.move_line_id.move_id.id)
        # Unlink the invoices and the payment order
        return self.with_context({"active_ids": inv_list}).invoice_free()
