##############################################################################
#
#    Copyright (C) 2014-2016 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from datetime import datetime

from odoo import models, fields, api


class EndContractWizard(models.TransientModel):
    _name = 'end.contract.wizard'
    _description = 'Recurring contract end wizard'

    contract_ids = fields.Many2many(
        'recurring.contract', string='Contracts',
        default=lambda self: self.env.context.get('active_ids'), readonly=False)
    end_reason_id = fields.Many2one(
        'recurring.contract.end.reason', required=True, readonly=False)
    end_date = fields.Datetime(default=fields.Datetime.now, required=True)
    additional_notes = fields.Text()

    @api.multi
    def end_contract(self):
        # Terminate contracts
        self.contract_ids.write({
            'end_reason_id': self.end_reason_id.id,
            'end_date': self.end_date
        })
        if self.additional_notes:
            self.contract_ids.message_post(self.additional_notes)
        now = datetime.now()
        end_date = self.end_date
        if end_date > now:
            # The contract will be ended by CRON later
            return True
        else:
            return self.contract_ids.action_contract_terminate()
