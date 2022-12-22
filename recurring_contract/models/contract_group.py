##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>, Steve Ferry, Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################

import logging

from odoo import fields, models, _
from odoo.tools import config

logger = logging.getLogger(__name__)
test_mode = config.get('test_enable')


class ContractGroup(models.Model):
    _name = 'recurring.contract.group'
    _description = 'A group of contracts'
    _inherit = 'mail.thread'
    _rec_name = 'ref'

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################
    advance_billing_months = fields.Integer(
        'Advance billing months',
        help='Advance billing allows you to generate invoices in '
             'advance. For example, you can generate the invoices '
             'for each month of the year and send them to the '
             'customer in january.', default=1)
    payment_mode_id = fields.Many2one(
        'account.payment.mode', 'Payment mode',
        domain=[('payment_type', '=', 'inbound')],
        tracking=True, readonly=False
    )
    last_paid_invoice_date = fields.Date(
        compute='_compute_last_paid_invoice',
        string='Last paid invoice date')
    partner_id = fields.Many2one(
        'res.partner', 'Partner', required=True,
        ondelete='cascade', tracking=True, readonly=False)
    ref = fields.Char('Reference')
    recurring_unit = fields.Selection([
        ('day', _('Day(s)')),
        ('week', _('Week(s)')),
        ('month', _('Month(s)')),
        ('year', _('Year(s)'))], 'Reccurency',
        default='month', required=True)
    recurring_value = fields.Integer(
        'Generate every', default=1, required=True)
    contract_ids = fields.One2many(
        'recurring.contract', 'group_id', 'Contracts', readonly=True)

    ##########################################################################
    #                             FIELDS METHODS                             #
    ##########################################################################
    def _compute_last_paid_invoice(self):
        for group in self:
            group.last_paid_invoice_date = max(
                [c.last_paid_invoice_date for c in group.contract_ids
                 if c.last_paid_invoice_date] or
                [False])

    ##########################################################################
    #                              ORM METHODS                               #
    ##########################################################################

    def write(self, vals):
        """
            Perform various check at contract modifications
            - Advance billing increased or decrease
            - Recurring value or unit changes
        """
        res = True
        res = super(ContractGroup, self).write(vals) & res
        self._updt_invoices_cg(vals)
        return res

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################
    def _get_gen_states(self):
        return ['active', 'waiting']

    def _updt_invoices_cg(self, vals):
        """ method to update invoices on contrat group (cg)
            :params vals dict of value that has been modified on the cg
        """
        if any(key in vals for key in ("payment_mode_id", "ref")):
            invoices = self.mapped("contract_ids.invoice_line_ids.move_id").filtered(
                lambda i: i.payment_state == "not_paid")
            if invoices:
                data_invs = dict()
                for inv in invoices:
                    data_invs.update(
                        inv._build_invoice_data(
                            ref=vals.get("ref"),
                            pay_mode_id=vals.get("payment_mode_id")
                        )
                    )
                invoices.update_invoices(data_invs)
        if "advance_billing_months" in vals:
            # In case the advance_billing_months is greater than before we should generate more invoices
            for contract in self.mapped("contract_ids"):
                contract.button_generate_invoices()
