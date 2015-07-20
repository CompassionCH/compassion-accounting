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

from openerp import api, fields, models, netsvc, _
from openerp import netsvc


class split_invoice_wizard(models.TransientModel):
    """Wizard for selecting invoice lines to be moved
    onto a new invoice."""
    _name = 'account.invoice.split.wizard'

    invoice_id = fields.Many2one(
        'account.invoice', default=lambda self: self._get_invoice())

    invoice_line_ids = fields.Many2many(
        'account.invoice.line', 'account_invoice_line_2_splitwizard',
        string='Invoice lines')

    @api.multi
    def _get_invoice_id(self):
        return self.env.context.get('active_id')

    @api.model
    def _get_invoice(self):
        return self.env.context.get('active_id')

        line_ids = [line.id for line in invoice.invoice_line]
        return line_ids

    @api.multi
    def split_invoice(self):
        self.ensure_one()
        invoice = False

        if self.invoice_line_ids:
            old_invoice = self.invoice_line_ids[0].invoice_id
            # to_move_lines = self.invoice_line_ids.filtered('split')
            invoice = self._copy_invoice(old_invoice)
            if old_invoice.state in ('draft', 'open'):
                uid = self.env.user.id
                cr = self.env.cr
                self.invoice_line_ids.write({'invoice_id': invoice.id})
                if old_invoice.state == 'open':
                    # Cancel and validate again invoices
                    old_invoice.action_cancel()
                    old_invoice.action_cancel_draft()
                    wf_service = netsvc.LocalService('workflow')
                    wf_service.trg_validate(
                        uid, 'account.invoice', old_invoice.id,
                        'invoice_open', cr)
                    wf_service.trg_validate(
                        uid, 'account.invoice', invoice.id, 'invoice_open',
                        cr)
        return invoice

    def _copy_invoice(self, old_invoice):
        # Create new invoice
        new_invoice = old_invoice.copy(
            default={'date_invoice': old_invoice.date_invoice})
        new_invoice.invoice_line.unlink()
        return new_invoice
