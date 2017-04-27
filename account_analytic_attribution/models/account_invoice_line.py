# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################
from openerp import api, models


class AccountInvoiceLine(models.Model):
    _inherit = "account.invoice.line"

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """
        TODO
        Select Analytic Account if an Attribution exists
        """
        res = super(AccountInvoiceLine, self)._onchange_product_id()
        self.account_analytic_id = self.env[
            'account.analytic.attribution'].account_get(
            self.product_id.id, self.partner_id.id, self.invoice_id.user_id.id,
            self.invoice_id.date_due
        ).id
        return res
