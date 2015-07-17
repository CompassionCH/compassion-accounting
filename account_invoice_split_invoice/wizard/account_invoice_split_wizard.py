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

from openerp import api, fields, models
from openerp.tools.translate import _
from openerp import netsvc
import pdb

class split_invoice_wizard(models.TransientModel):
    """Wizard for selecting invoice lines to be moved
    onto a new invoice."""
    _name = 'account.invoice.split.wizard'

    @api.multi
    def _get_invoice_id(self):
        return self.env.context.get('active_id')

    @api.multi
    def _get_invoice_line_ids(self):
        active_id = self.env.context.get('active_id')
        invoice = self.env['account.invoice'].browse(active_id)

        line_ids = [line.id for line in invoice.invoice_line]
        return line_ids

    @api.one
    def _write_lines(self):
        """Update invoice_lines. Those that have the invoice_id removed
        are attached to a new draft invoice."""
        invoice_id = False

        if self.invoice_line_ids:
            inv_line_update = self.invoice_line_ids
            old_invoice = self.invoice_line_ids[0].invoice_id
            invoice_id = old_invoice
            if old_invoice.state in ('draft', 'open'):
                invoice_id = self._copy_invoice(old_invoice)
                uid = self.env.user.id
                cr = self.env.cr
                inv_line_update.write({'invoice_id': invoice_id.id})
                if old_invoice.state == 'open':
                    # Cancel and validate again invoices
                    old_invoice.action_cancel()
                    old_invoice.action_cancel_draft()
                    wf_service = netsvc.LocalService('workflow')
                    wf_service.trg_validate(
                        uid, 'account.invoice', old_invoice.id,
                        'invoice_open', cr)
                    wf_service.trg_validate(
                        uid, 'account.invoice', invoice_id.id, 'invoice_open',
                        cr)
        return invoice_id

    def _copy_invoice(self, old_invoice):
        # Create new invoice
        new_invoice = old_invoice.copy(
            default={'date_invoice': old_invoice.date_invoice})
        new_invoice.invoice_line.unlink()
        return new_invoice

    invoice_id = fields.Many2one('account.invoice', 'Invoice',
                                 compute='_get_invoice_id')

    invoice_line_ids = fields.Many2many(
        'account.invoice.line', 'id', inverse="_write_lines",
        default=_get_invoice_line_ids, compute='_get_invoice_line_ids',
        string=_('Invoice lines'))

    @api.multi
    def split_invoice(self):
        # Nothing to do here
        return True
