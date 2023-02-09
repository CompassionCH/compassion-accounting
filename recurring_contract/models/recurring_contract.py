##############################################################################
#
#    Copyright (C) 2014 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import calendar
import logging
import os
from datetime import datetime, date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import flatten, config

_logger = logging.getLogger(__name__)


class RecurringContract(models.Model):
    """ A contract to perform recurring invoicing to a partner """

    _name = "recurring.contract"
    _description = "Recurring contract"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'utm.mixin']
    _rec_name = 'reference'
    _order = "start_date desc"

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################

    reference = fields.Char(
        default="/", required=True, readonly=True,
        states={'draft': [('readonly', False)]}, copy=False)
    start_date = fields.Datetime(
        readonly=True, states={'draft': [('readonly', False)]},
        copy=False, tracking=True)
    end_date = fields.Datetime(
        readonly=False, states={'terminated': [('readonly', True)]},
        tracking=True, copy=False)
    end_reason_id = fields.Many2one(
        'recurring.contract.end.reason', 'End reason', copy=False,
        ondelete='restrict', readonly=False
    )
    last_paid_invoice_date = fields.Date(
        compute='_compute_last_paid_invoice')
    partner_id = fields.Many2one(
        'res.partner', 'Partner', required=True, readonly=True,
        states={'draft': [('readonly', False)]}, ondelete='restrict',
        index=True
    )
    group_id = fields.Many2one(
        'recurring.contract.group', 'Payment Options',
        required=True, ondelete='restrict', tracking=True, readonly=False)
    invoice_line_ids = fields.One2many(
        'account.move.line', 'contract_id',
        'Related invoice lines', readonly=True, copy=False)
    contract_line_ids = fields.One2many(
        'recurring.contract.line', 'contract_id',
        'Contract lines', tracking=True, copy=True, readonly=False)
    state = fields.Selection(
        [
            ('draft', _('Draft')),
            ('waiting', _('Waiting Payment')),
            ('active', _('Active')),
            ('terminated', _('Terminated')),
            ('cancelled', _('Cancelled'))
        ], default='draft', readonly=True,
        tracking=True, copy=False, index=True)
    total_amount = fields.Float(
        'Total', compute='_compute_total_amount',
        tracking=True, store=True)
    payment_mode_id = fields.Many2one(
        'account.payment.mode', string='Payment mode',
        related='group_id.payment_mode_id', readonly=True, store=True)
    nb_invoices = fields.Integer(compute="_compute_invoices")
    activation_date = fields.Datetime(readonly=True, copy=False)
    company_id = fields.Many2one(
        'res.company',
        'Company',
        required=True,
        default=lambda self: self.env.user.company_id.id, readonly=False
    )
    pricelist_id = fields.Many2one(
        'product.pricelist',
        'Pricelist',
        domain="[('company_id', '=', company_id)]",
        required=True,
        readonly=False
    )
    comment = fields.Text()
    due_invoice_ids = fields.Many2many(
        "account.move", string="Late invoices", compute="_compute_due_invoices", store=True
    )
    amount_due = fields.Integer(compute="_compute_due_invoices", store=True)
    months_due = fields.Integer(
        compute="_compute_due_invoices", store=True,
        help="Number of unpaid months (in the past)")
    period_paid = fields.Boolean(
        compute="_compute_period_paid",
        help="Tells if the advance billing period is already paid",
    )
    months_paid = fields.Integer(
        compute="_compute_months_paid",
        help="Number indicating up to which month the contract is paid (<1=prev. year,1=Jan,12=December,>12=next year)")
    missing_invoices = fields.Boolean(
        compute="_compute_missing_invoices",
        help="Tells if invoices have not been generated yet",
        store=True
    )

    _sql_constraints = [
        ('unique_ref', "unique(reference)", "Reference must be unique!"),
    ]

    ##########################################################################
    #                             FIELDS METHODS                             #
    ##########################################################################
    def _compute_invoices(self):
        for contract in self:
            contract.nb_invoices = len(
                contract.mapped('invoice_line_ids.move_id').filtered(
                    lambda i: i.state not in ('cancel', 'draft')
                              and i.payment_state != 'paid'
                ))

    @api.depends('contract_line_ids', 'contract_line_ids.amount',
                 'contract_line_ids.quantity')
    def _compute_total_amount(self):
        for contract in self:
            contract.total_amount = sum([
                line.subtotal for line in contract.contract_line_ids
            ])

    def _compute_last_paid_invoice(self):
        for contract in self:
            contract.last_paid_invoice_date = max(
                [invl.move_id.invoice_date for invl in
                 contract.invoice_line_ids if invl.move_id.payment_state == 'paid'] or [False])

    @api.depends("invoice_line_ids", "invoice_line_ids.payment_state")
    def _compute_due_invoices(self):
        for contract in self:
            due_invoices = contract._filter_due_invoices()
            contract.due_invoice_ids = due_invoices
            contract.amount_due = int(sum(due_invoices.mapped("amount_total")))
            months = set()
            for invoice in due_invoices:
                idate = invoice.date
                months.add((idate.month, idate.year))
            contract.months_due = len(months)

    def _filter_due_invoices(self):
        # Use SQL for better performance
        this_month = date.today().replace(day=1)
        self.env.cr.execute("""
            SELECT move_id
            FROM account_move_line
            WHERE contract_id = ANY(%s) AND payment_state != 'paid' AND due_date < %s;
        """, [self.ids, fields.Date.to_string(this_month)])
        move_ids = flatten(self.env.cr.fetchall())
        moves = self.env["account.move"]
        if move_ids:
            moves = moves.browse(move_ids)
        return moves

    def _compute_period_paid(self):
        for contract in self:
            advance_billing = contract.group_id.advance_billing_months
            this_month = date.today().month
            # Don't consider next year in the period to pay
            to_pay_period = min(this_month + advance_billing, 12)
            # Exception for december, we will consider next year
            if this_month == 12:
                to_pay_period += advance_billing
            contract.period_paid = contract.months_paid >= to_pay_period

    def _compute_months_paid(self):
        """This is a query returning the number of months paid for the current year."""
        self._cr.execute(
            "SELECT contract_id, count(contract_id) AS paid_month "
            "FROM account_move_line "
            "WHERE payment_state = 'paid' "
            f"AND contract_id IN ({', '.join(str(contract_id) for contract_id in self.ids)}) "
            "AND EXTRACT(year FROM last_payment) = EXTRACT(year FROM CURRENT_DATE) "
            "GROUP BY contract_id "
        )
        res = self._cr.dictfetchall()
        dict_contract_id_paidmonth = {
            row["contract_id"]: row["paid_month"] or 0 for row in res
        }
        for contract in self:
            contract.months_paid = dict_contract_id_paidmonth.get(contract.id)

    @api.depends("invoice_line_ids", "state")
    def _compute_missing_invoices(self):
        query = """
            SELECT COUNT(*)
            FROM account_move_line
            WHERE contract_id = %s AND product_id = ANY(%s)
            AND due_date BETWEEN NOW() AND NOW() + INTERVAL '%s MONTHS'
        """
        for contract in self:
            if contract.state in ("waiting", "active"):
                group = contract.group_id
                self.env.cr.execute(query, [
                    contract.id,
                    contract.mapped("contract_line_ids.product_id").ids,
                    group.advance_billing_months]
                                    )
                number_invoices = self.env.cr.fetchone()[0]
                if group.recurring_unit == "month":
                    contract.missing_invoices = number_invoices < (
                            group.advance_billing_months // group.recurring_value)
                else:
                    # This is the yearly case, there should be at least one invoice per year.
                    contract.missing_invoices = number_invoices == 0
            else:
                contract.missing_invoices = False

    ##########################################################################
    #                              ORM METHODS                               #
    ##########################################################################

    @api.model
    def create(self, vals):
        """ Add a sequence generated ref if none is given """
        if vals.get('reference', '/') == '/':
            vals['reference'] = self.env['ir.sequence'].next_by_code(
                'recurring.contract.ref')

        return super().create(vals)

    def write(self, vals):
        """ Perform various checks when a contract is modified. """
        res = super().write(vals)

        if "partner_id" in vals:
            self.mapped("group_id").write({"partner_id": vals["partner_id"]})

        self._updt_invoices_rc(vals)

        return res

    def unlink(self):
        if self.filtered('start_date') and not self.env.context.get("force_delete"):
            raise UserError(
                _('You cannot delete a validated contract.'))
        return super().unlink()

    ##########################################################################
    #                             PUBLIC METHODS                             #
    ##########################################################################
    def button_generate_invoices(self):
        return self.mapped("group_id").button_generate_invoices()

    def generate_invoices(self):
        """ By default, launch asynchronous job to perform the task.
            Context value async_mode set to False can force to perform
            the task immediately.
        """
        self.mapped("group_id").generate_invoices()

    def cancel_contract_invoices(self):
        """ By default, launch asynchronous job to perform the task.
            Context value async_mode set to False can force to perform
            the task immediately.
        """
        if self.env.context.get('async_mode', True):
            self.with_delay()._cancel_invoices()
        else:
            self._cancel_invoices()

    ##########################################################################
    #                             VIEW CALLBACKS                             #
    ##########################################################################
    @api.onchange('partner_id')
    def on_change_partner_id(self):
        """ On partner change, we update the group_id. If partner has
        only 1 group, we take it. Else, we take nothing.
        We also update the company_id when the partner have a country_id
        """
        group_ids = self.env['recurring.contract.group'].search(
            [('partner_id', '=', self.partner_id.id)])
        if len(group_ids) == 1:
            self.group_id = group_ids
        else:
            self.group_id = False

        # Update the company value based on the partner.country_id as there is no value for partner.company_id
        company_ids = self.env['res.company'].search([])
        self.company_id = company_ids.filtered(lambda l: l.country_id == self.partner_id.country_id)

    @api.onchange('company_id')
    def on_change_company_id(self):
        """ On company change, we update the pricelist_id dropdown list.
        So that the list offers company currency or EUR as a choice """
        pricelist = self.env["product.pricelist"].search([('company_id', '=', self.company_id.id)])

        # Set pricelist if there is a result
        if pricelist:
            # Take first result
            self.pricelist_id = pricelist[0]
        # Unset pricelist_id if the company selected doesn't have one
        else:
            self.pricelist_id = False

    def open_invoices(self):
        self.ensure_one()
        invoice_ids = self.mapped('invoice_line_ids.move_id').ids
        return {
            'name': _('Contract invoices'),
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'domain': [('id', 'in', invoice_ids)],
            'target': 'current',
            "context": {"search_default_unpaid": 1}
        }

    ##########################################################################
    #                            WORKFLOW METHODS                            #
    ##########################################################################
    def contract_draft(self):
        if self.filtered(lambda c: c.state == 'active'):
            raise UserError(_("Active contract cannot be put to draft"))
        self.write({'state': 'draft'})
        return True

    def contract_waiting(self):
        if self.filtered(lambda c: c.state == 'active'):
            raise UserError(_("Active contract cannot be put to waiting"))
        if self.filtered(lambda c: not c.total_amount):
            raise UserError(_("Please configure contract lines"))
        self.write({
            'state': 'waiting',
            'start_date': fields.Datetime.now()
        })
        self.generate_invoices()
        return True

    def contract_active(self):
        if self.filtered(lambda c: c.state != 'waiting'):
            raise UserError(_('Only validated contracts can be activated.'))
        self.write({
            'state': 'active',
            'activation_date': fields.Datetime.now(),
        })
        return True

    def action_contract_terminate(self):
        """
        Action for finishing a contract. It will go in either 'terminated'
        or 'cancelled' state depending if it was active or not.
        :return: True
        """
        active_contracts = self.filtered('activation_date')
        if active_contracts:
            active_contracts.contract_terminated()
        inactive = self - active_contracts
        if inactive:
            inactive.contract_cancelled()
        self.cancel_contract_invoices()
        return True

    def contract_terminated(self):
        now = fields.Datetime.now()
        self.write({
            'state': 'terminated',
            'end_date': now
        })
        return True

    def contract_cancelled(self):
        today = fields.Datetime.now()
        self.write({
            'state': 'cancelled',
            'end_date': today
        })
        return True

    def action_cancel_draft(self):
        """ Set back a cancelled contract to draft state. """
        if self.filtered(lambda c: c.state != 'cancelled'):
            raise UserError(_("Only cancelled contracts can be set back to "
                              "draft."))
        self.write({
            'state': 'draft',
            'end_date': False,
            'activation_date': False,
            'start_date': False,
            'end_reason_id': False
        })
        return True

    def force_activation(self):
        """ Used to transition contracts in active state. """
        self.filtered(lambda c: c.state == 'draft').contract_waiting()
        self.contract_active()
        return True

    def invoice_unpaid(self, invoice):
        """ Hook when invoice is unpaid """
        pass

    def invoice_paid(self, invoice):
        """ Activate contract if it is waiting for payment. """
        activate_contracts = self.filtered(lambda c: c.state == 'waiting')
        if activate_contracts:
            activate_contracts.contract_active()

    @api.model
    def end_date_reached(self):
        now = fields.Datetime.now()
        expired = self.search([
            ('end_date', '>=', now),
            ('state', 'not in', ['cancelled', 'terminated'])
        ])
        return expired.action_contract_terminate()

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################
    def _cancel_invoices(self):
        """ Cancel invoices
            This method cancel invoices that are due in the future
            When the sponsor has paid in advance, we cancel the paid
            invoices and let the user decide what to do with the payment.
        """
        _logger.info("clean invoices called.")
        for contract in self:
            # We "gift" the last month so we search from the first of that last month
            since_date = contract.end_date.date().replace(day=1)
            # Cancel invoices paid
            inv_lines_paid = contract.invoice_line_ids.filtered(
                lambda l: l.payment_state == 'paid' and l.due_date >= since_date)
            move_lines = inv_lines_paid.mapped('move_id.line_ids').filtered('reconciled')
            reconciles = inv_lines_paid.mapped('move_id.line_ids.full_reconcile_id')

            # Unreconcile paid invoices
            move_lines |= reconciles.mapped('reconciled_line_ids')
            move_lines.remove_move_reconcile()
            paid_invoices = move_lines.mapped('move_id.invoice_line_ids').filtered(
                lambda l: l.contract_id not in self).mapped('move_id')
            paid_invoices.reconcile_after_clean()

            # Cancel open invoices
            invoices_lines = contract.invoice_line_ids.filtered(
                lambda l: l.payment_state != 'paid' and l.due_date >= since_date)
            # Multi contracts invoices should delete just their lines
            empty_invoices = self.env['account.move']
            to_remove_invl = self.env['account.move.line']
            invoices = invoices_lines.mapped("move_id")
            for inv_line in invoices_lines:
                invoice = inv_line.move_id
                # Check if invoice is empty after removing the invoice_lines
                # of the given contract
                remaining_lines = invoice.invoice_line_ids.filtered(
                    lambda l: not l.contract_id or l.contract_id not in self)
                if remaining_lines:
                    # We can move or remove the line
                    to_remove_invl |= inv_line
                else:
                    # The invoice would be empty if we remove the line
                    empty_invoices |= invoice
            empty_invoices.button_cancel()
            renew_invs = invoices - empty_invoices
            to_remove_invl.unlink()
            if renew_invs:
                # Invoices to set back in open state
                renew_invs.action_post()
            _logger.info(str(len(invoices)) + " invoices cleaned.")

    def _updt_invoices_rc(self, vals):
        """
        It updates the invoices of a contract when the contract is updated

        :param vals: the values that are being updated on the contract
        """
        if any(key in vals for key in ("group_id", "contract_line_ids", "birthday_invoice", "christmas_invoice")):
            data_invs = {}
            for contract in self:
                for inv in contract.mapped("invoice_line_ids.move_id").filtered(
                        lambda m: m.payment_state == "not_paid" and m.state != "cancel"):
                    data_invs.update(
                        inv._build_invoice_data(
                            contract=contract,
                            ref=contract.group_id.ref,
                            pay_mode_id=contract.group_id.payment_mode_id
                        )
                    )
            if data_invs:
                self.mapped("invoice_line_ids.move_id").update_invoices(data_invs)
