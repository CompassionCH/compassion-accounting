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

from openerp import exceptions, fields, models, api
from openerp.tools.translate import _


class recurring_invoicer_wizard(models.TransientModel):

    ''' This wizard generate invoices from contract groups when launched.
    By default, all contract groups are used.
    '''
    _name = 'recurring.invoicer.wizard'

    invoice_ids = fields.One2many(
        'account.invoice', 'recurring_invoicer_id',
        _('Generated invoices'), readonly=True)
    generation_date = fields.Date(_('Generation date'), readonly=True)

    @api.one
    def generate(self, *args, **kwargs):
        recurring_invoicer_obj = self.env['recurring.invoicer']
        contract_groups = self.env['recurring.contract.group'].search([])
        invoicer = recurring_invoicer_obj.create({'source': self._name})

        contract_groups.generate_invoices(invoicer)
        if not invoicer.invoice_ids:
            raise exceptions.Warning('ZeroGenerationError',
                                     _('0 invoices have been generated.'))

        return {
            'name': 'recurring.invoicer.form',
            'view_mode': 'form',
            'view_type': 'form,tree',
            'res_id': invoicer.id,  # id of the object to which to redirect
            'res_model': 'recurring.invoicer',  # object name
            'type': 'ir.actions.act_window',
        }

    @api.model
    def generate_from_cron(self, *args, **kwargs):
        self.generate()
