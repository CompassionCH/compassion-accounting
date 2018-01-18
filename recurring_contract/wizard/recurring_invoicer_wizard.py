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

from odoo import fields, models, api
import datetime
from dateutil.relativedelta import relativedelta


class InvoicerWizard(models.TransientModel):

    ''' This wizard generate invoices from contract groups when launched.
    By default, all contract groups are used.
    '''
    _name = 'recurring.invoicer.wizard'

    generation_date = fields.Date(readonly=True)

    @api.multi
    def generate(self):
        date_limit = datetime.date.today() + relativedelta(day=1, months=+1)

        recurring_invoicer_obj = self.env['recurring.invoicer']
        contract_groups = self.env['recurring.contract.group'].search([
            ('next_invoice_date', '<', date_limit),
            ('next_invoice_date', '!=', False)])

        invoicer = recurring_invoicer_obj.create({'source': self._name})

        contract_groups.generate_invoices(invoicer)

        return {
            'name': 'recurring.invoicer.form',
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': invoicer.id,  # id of the object to which to redirect
            'res_model': 'recurring.invoicer',  # object name
            'type': 'ir.actions.act_window',
        }

    @api.model
    def generate_from_cron(self):
        self.generate()
        return True
