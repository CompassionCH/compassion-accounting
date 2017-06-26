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

from datetime import datetime

from odoo import api, fields, models
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF

import logging

logger = logging.getLogger(__name__)


class RecurringInvoicer(models.Model):
    ''' An invoicer holds a bunch of invoices that have been generated
    in the same context. It also makes the validating or cancelling process
    of these contracts easy.
    '''
    _name = 'recurring.invoicer'
    _rec_name = 'identifier'
    _order = 'generation_date desc'

    identifier = fields.Char(
        required=True, default=lambda self: self.calculate_id())
    source = fields.Char('Source model', required=True)
    generation_date = fields.Date(default=datetime.today().strftime(DF))
    invoice_ids = fields.One2many(
        'account.invoice', 'recurring_invoicer_id',
        'Generated invoices')

    def calculate_id(self):
        return self.env['ir.sequence'].next_by_code('rec.invoicer.ident')

    @api.multi
    def validate_invoices(self):
        ''' Validates created invoices (set state from draft to open)'''
        self.ensure_one()
        invoice_to_validate = self.invoice_ids.filtered(
            lambda invoice: invoice.state == 'draft')

        logger.info("Invoice validation started.")
        count = 1
        nb_invoice = len(invoice_to_validate)
        for invoice in invoice_to_validate:
            logger.info("Validating invoice {0}/{1}".format(
                        count, nb_invoice))
            invoice.action_invoice_open()
            # After an invoice is validated, we commit all writes in order to
            # avoid doing it again in case of an error or a timeout
            self.env.cr.commit()
            count += 1
        return invoice_to_validate

    @api.multi
    def cancel_invoices(self):
        ''' Cancel created invoices (set state from open to cancelled) '''
        invoice_to_cancel = self.mapped('invoice_ids').filtered(
            lambda invoice: invoice.state != 'cancel')

        invoice_to_cancel.action_invoice_cancel()

        return True
