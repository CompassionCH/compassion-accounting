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

from openerp import api, exceptions, fields, models, netsvc
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from openerp.tools.translate import _

import logging

logger = logging.getLogger(__name__)


class recurring_invoicer(models.Model):
    ''' An invoicer holds a bunch of invoices that have been generated
    in the same context. It also makes the validating or cancelling process
    of these contracts easy.
    '''
    _name = 'recurring.invoicer'
    _rec_name = 'identifier'

    def calculate_id(self):
        return self.env['ir.sequence'].next_by_code('rec.invoicer.ident')

    identifier = fields.Char(_('Identifier'), required=True,
                             default=calculate_id)
    source = fields.Char(_('Source model'), required=True)
    generation_date = fields.Date(
        _('Generation date'), default=datetime.today().strftime(DF))
    invoice_ids = fields.One2many(
        'account.invoice', 'recurring_invoicer_id',
        _('Generated invoices'))

    @api.one
    def validate_invoices(self):
        ''' Validates created invoices (set state from draft to open)'''
        # Setup a popup message ?
        invoice_to_validate = self.invoice_ids.filtered(
            lambda invoice: invoice.state == 'draft')

        if not invoice_to_validate:
            raise exceptions.Warning('SelectionError',
                                     _('There is no invoice to validate'))

        wf_service = netsvc.LocalService('workflow')
        logger.info("Invoice validation started.")
        count = 1
        nb_invoice = len(invoice_to_validate)
        for invoice in invoice_to_validate:
            logger.info("Validating invoice {0}/{1}".format(
                        count, nb_invoice))
            wf_service.trg_validate(self.env.user.id, 'account.invoice',
                                    invoice.id, 'invoice_open', self.env.cr)
            # After an invoice is validated, we commit all writes in order to
            # avoid doing it again in case of an error or a timeout
            self.env.cr.commit()
            count += 1
        return invoice_to_validate

    # When an invoice is cancelled, should we adjust next_invoice_date
    # in contract ?
    @api.one
    def cancel_invoices(self):
        ''' Cancel created invoices (set state from open to cancelled) '''
        invoice_to_cancel = self.invoice_ids.filtered(
            lambda invoice: invoice.state != 'cancel')

        if not invoice_to_cancel:
            raise exceptions.Warning('SelectionError',
                                     _('There is no invoice to cancel'))

        wf_service = netsvc.LocalService('workflow')
        for invoice in invoice_to_cancel:
            wf_service.trg_validate(self.env.user.id, 'account.invoice',
                                    invoice.id, 'invoice_cancel', self.env.cr)
        return True
