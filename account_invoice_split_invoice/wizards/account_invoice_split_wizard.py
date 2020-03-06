##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, fields, models


class SplitInvoiceWizard(models.TransientModel):
    """Wizard for selecting invoice lines to be moved
    onto a new invoice."""
    _name = 'account.invoice.split.wizard'
    _description = 'Split Invoice Wizard'

    invoice_id = fields.Many2one(
        'account.invoice', default=lambda self: self._get_invoice(), readonly=False)

    invoice_line_ids = fields.Many2many(
        'account.invoice.line', 'account_invoice_line_2_splitwizard',
        string='Invoice lines', readonly=False)

    @api.model
    def _get_invoice(self):
        return self.env.context.get('active_id')

    @api.multi
    def split_invoice(self):
        self.ensure_one()
        invoice = False

        if self.invoice_line_ids:
            old_invoice = self.invoice_line_ids[0].invoice_id
            if old_invoice.state in ('draft', 'open'):
                invoice = self._copy_invoice(old_invoice)
                was_open = old_invoice.state == 'open'
                if was_open:
                    old_invoice.action_invoice_cancel()
                    old_invoice.action_invoice_draft()
                    old_invoice.env.clear()
                self.invoice_line_ids.write({'invoice_id': invoice.id})
                if was_open:
                    old_invoice.action_invoice_open()
                    invoice.action_invoice_open()
        return invoice

    def _copy_invoice(self, old_invoice):
        # Create new invoice
        new_invoice = old_invoice.copy(
            default={'date_invoice': old_invoice.date_invoice})
        new_invoice.invoice_line_ids.unlink()
        return new_invoice
