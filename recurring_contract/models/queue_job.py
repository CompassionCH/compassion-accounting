# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, models, _


class QueueJob(models.Model):
    _inherit = 'queue.job'

    @api.multi
    def related_action_invoicer(self, invoicer=None):
        self.ensure_one()
        action = {
            'name': _("Invoicer"),
            'type': 'ir.actions.act_window',
            'res_model': 'recurring.invoicer',
            'view_type': 'form',
            'view_mode': 'form',
            'res_id': invoicer and invoicer.id,
        }
        return action

    @api.multi
    def related_action_contract(self):
        contract_ids = self.record_ids
        action = {
            'name': _("Contract"),
            'type': 'ir.actions.act_window',
            'res_model': 'recurring.contract',
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_id': contract_ids[0],
            'domain': [('id', 'in', contract_ids)],
            'context': {'default_type': 'S'},
        }
        return action
