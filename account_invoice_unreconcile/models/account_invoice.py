# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2016 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

from openerp import api, models


class AccountInvoice(models.Model):
    """
    Add method to easily unreconcile payments.
    """
    _inherit = 'account.invoice'

    @api.multi
    def button_unreconcile(self):
        self.mapped('payment_ids.reconcile_id').unlink()
        return True
