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
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

logger = logging.getLogger(__name__)
test_mode = config.get("test_enable")

_logger = logging.getLogger(__name__)

ERROR_MESSAGE = "The {} of the linked contract should be the same for every contracts."


class ContractGroup(models.Model):
    _name = "recurring.contract.group"
    _description = "A group of contracts"
    _inherit = "mail.thread"
    _rec_name = "ref"

    ##########################################################################
    #                                 FIELDS                                 #
    ##########################################################################
    advance_billing_months = fields.Integer(
        "Advance billing months",
        required=True,
        help="Advance billing allows you to generate invoices in "
        "advance. For example, you can generate the invoices "
        "for each month of the year and send them to the "
        "customer in january.",
        default=1,
    )
    payment_mode_id = fields.Many2one(
        "account.payment.mode",
        "Payment mode",
        domain=[("payment_type", "=", "inbound")],
        tracking=True,
        readonly=False,
    )
    last_paid_invoice_date = fields.Date(
        compute="_compute_last_paid_invoice", string="Last paid invoice date"
    )
    nb_invoices = fields.Integer(compute="_compute_invoices")
    # Define the next time a partner should rereceive an invoice
    invoice_suspended_until = fields.Date(
        string="Invoice Suspended Until",
        help="Date at which the sponsor should receive invoices again.",
        tracking=True,
        states={"draft": [("readonly", False)]},
    )
    partner_id = fields.Many2one(
        "res.partner",
        "Partner",
        required=True,
        ondelete="cascade",
        tracking=True,
        readonly=False,
    )
    ref = fields.Char("Reference", tracking=True)
    recurring_unit = fields.Selection(
        [("month", _("Month(s)")), ("year", _("Year(s)"))],
        "Recurrence",
        default="month",
        required=True,
    )
    recurring_value = fields.Integer("Generate every", default=1, required=True)
    month_interval = fields.Integer(compute="_compute_month_interval")
    contract_ids = fields.One2many(
        "recurring.contract", "group_id", "Contracts", readonly=True
    )
    active_contract_ids = fields.One2many(
        "recurring.contract",
        "group_id",
        "Active contracts",
        compute="_compute_active_contracts",
    )
    current_invoice_date = fields.Date(
        compute="_compute_current_invoice_date",
        help="Gives the current invoice date for the contract group, "
        "either the current month or the next one depending the settings.",
    )

    ##########################################################################
    #                             FIELDS METHODS                             #
    ##########################################################################
    @api.depends("contract_ids")
    def _compute_active_contracts(self):
        for pay_opt in self:
            pay_opt.active_contract_ids = pay_opt.contract_ids.filtered(
                lambda c: c.state in ("active", "waiting")
            )

    def _compute_last_paid_invoice(self):
        for group in self:
            group.last_paid_invoice_date = max(
                [
                    c.last_paid_invoice_date
                    for c in group.active_contract_ids
                    if c.last_paid_invoice_date
                ]
                or [False]
            )

    def _compute_invoices(self):
        for pay_opt in self:
            pay_opt.nb_invoices = len(
                pay_opt.mapped("active_contract_ids.invoice_line_ids.move_id").filtered(
                    lambda i: i.state not in ("cancel", "draft")
                    and i.payment_state != "paid"
                )
            )

    @api.constrains("contract_ids")
    def _same_company_all_contract(self):
        """
        The contract linked to a payment options should be on the same company
        and only one pricelist possible.
        """
        for pay_opt in self:
            active_contracts = pay_opt.active_contract_ids
            if active_contracts:
                company_to_match = active_contracts[0].company_id
                pricelist_to_match = active_contracts[0].pricelist_id
                for contract in active_contracts:
                    if contract.company_id != company_to_match:
                        raise UserError(ERROR_MESSAGE.format("companies"))
                    if contract.company_id != pricelist_to_match:
                        raise UserError(ERROR_MESSAGE.format("pricelists"))

    @staticmethod
    def day_selection():
        return [(str(day), str(day)) for day in range(1, 32)]

    def _compute_month_interval(self):
        for group in self:
            group.month_interval = group.recurring_value * (
                1 if group.recurring_unit == "month" else 12
            )

    def _compute_current_invoice_date(self):
        for group in self:
            start_date, offset = group._calculate_start_date_and_offset()
            group.current_invoice_date = start_date + relativedelta(months=offset)

    ##########################################################################
    #                              ORM METHODS                               #
    ##########################################################################
    def write(self, vals):
        """
        Perform various check at contract modifications
        - Advance billing increased or decrease
        - Recurring value or unit changes
        """
        if vals.get("invoice_suspended_until"):
            if (
                fields.Date.from_string(vals["invoice_suspended_until"])
                < datetime.today().date()
            ):
                raise UserError(
                    _(
                        "The suspension of invoices has to be in the future ! "
                        "(Invoice Suspended Until field)"
                    )
                )
        res = super().write(vals)
        self._updt_invoices_cg(vals)
        return res

    ##########################################################################
    #                              VIEWS ACTIONS                             #
    ##########################################################################
    def open_invoices(self):
        self.ensure_one()
        invoice_ids = self.mapped("active_contract_ids.invoice_line_ids.move_id").ids
        return {
            "name": _("Contract invoices"),
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "res_model": "account.move",
            "domain": [("id", "in", invoice_ids)],
            "target": "current",
            "context": {"search_default_unpaid": 1},
        }

    def button_generate_invoices(self, contract_id=None):
        """Immediately generate invoices for the contract group."""
        invoicer = (
            self.with_context({"async_mode": False})
            .with_company(self.active_contract_ids[0].company_id)
            .generate_invoices(contract_id)
        )
        if invoicer.invoice_ids:
            notification_type = "success"
            msg = "The generation was successfully processed."
        else:
            notification_type = "info"
            msg = (
                "The generation didn't created any new invoices. This could "
                "be because the sponsorship already have the correct invoices open."
            )
        notification = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": ("Generation of Invoices"),
                "message": msg,
                "type": f"{notification_type}",
            },
        }
        return notification

    ##########################################################################
    #                             PRIVATE METHODS                            #
    ##########################################################################
    def generate_invoices(self, contract_id=None):
        """By default, launch asynchronous job to perform the task.
        Context value async_mode set to False can force to perform
        the task immediately.
        """
        invoicer = self.env["recurring.invoicer"].create({})
        if self.env.context.get("async_mode", True):
            for group in self:
                group.with_delay()._generate_invoices(invoicer, contract_id)
        else:
            self._generate_invoices(invoicer, contract_id)
        return invoicer

    def _generate_invoices(self, invoicer, contract_id=None):
        """Checks all contracts and generate invoices if needed.
        Create an invoice per contract group per date.
        """
        _logger.info(
            f"Starting generation of invoices for contract groups : {self.ids}"
        )

        # Set to track processed invoices to avoid duplication
        processed_invoices = set()

        contract = None
        if contract_id:
            contract = self.env["recurring.contract"].browse(contract_id)
            if not contract:
                _logger.error(f"The contract with the id {contract_id} does not exist.")
                return False

        for group in self:
            # Calculate the initial invoicing date and starting offset
            invoicing_date, starting_offset = group._calculate_start_date_and_offset()

            # Iterate through invoice offsets to generate invoices
            for invoice_offset in range(
                starting_offset, group.advance_billing_months + 1, group.month_interval
            ):
                # Calculate the current invoicing date for this offset
                current_invoicing_date = invoicing_date + relativedelta(
                    months=invoice_offset
                )

                # Check if invoice generation should be skipped for this date
                if group._should_skip_invoice_generation(
                    current_invoicing_date, contract
                ):
                    continue

                # Create a unique key for the invoice to track it
                invoice_key = (group.id, current_invoicing_date)

                # Check if the invoice for this key has already been processed
                if invoice_key not in processed_invoices:
                    # Process invoice generation if not already processed
                    group._process_invoice_generation(
                        invoicer, current_invoicing_date, contract
                    )
                    # Add the invoice key to the set of processed invoices
                    processed_invoices.add(invoice_key)

        # Refresh state to check whether invoices are missing in some contracts
        self.mapped("active_contract_ids")._compute_missing_invoices()
        _logger.info("Process successfully generated invoices")
        return True

    def _calculate_start_date_and_offset(self):
        """
        Calculate the start date and the offset
        to know if we should generate the current month or not.
        Start date will be the first of the current month and the offset will be 1
        if the next invoice should be for the next month.
        @return: date, int
        """
        self.ensure_one()
        company = self.mapped("active_contract_ids.company_id")
        settings_obj = self.env["res.config.settings"].sudo().with_company(company.id)
        curr_month = settings_obj.get_param_multi_company(
            "recurring_contract.do_generate_curr_month"
        )
        block_day = settings_obj.get_param_multi_company(
            "recurring_contract.invoice_block_day"
        )
        today = date.today()
        start_date = today.replace(day=1)
        offset = 0
        if curr_month != "True" or today.day > int(block_day):
            offset = 1
        return start_date, offset

    def _should_skip_invoice_generation(self, invoicing_date, contract=None):
        """In such cases, we should skip the invoice generation:
        - There is already an invoice for this due date which has been cancelled or
          edited.
        - Contract group suspension.
        - A specific contract is given and an invoice for this due date already exists
          and isn't cancelled.
        """
        self.ensure_one()

        if contract:
            search_filter = [
                ("state", "!=", "cancel"),
                ("invoice_date_due", "=", invoicing_date),
                ("partner_id", "=", self.partner_id.id),
                ("move_type", "=", "out_invoice"),
                ("line_ids.contract_id", "=", contract.id),
                (
                    "line_ids.product_id",
                    "in",
                    contract.product_ids.ids,
                ),
            ]
        else:
            search_filter = [
                ("invoice_date_due", "=", invoicing_date),
                ("partner_id", "=", self.partner_id.id),
                ("move_type", "=", "out_invoice"),
                ("line_ids.contract_id", "in", self.active_contract_ids.ids),
                (
                    "line_ids.product_id",
                    "in",
                    self.active_contract_ids.mapped("product_ids").ids,
                ),
                "|",
                ("payment_state", "not in", ["paid", "not_paid"]),
                ("state", "=", "cancel"),
            ]

        existing_invoices = self.env["account.move"].search_count(search_filter)

        is_suspended = (
            self.invoice_suspended_until
            and self.invoice_suspended_until > invoicing_date
        )

        return bool(existing_invoices) or is_suspended

    def _process_invoice_generation(self, invoicer, invoicing_date, contract=None):
        self.ensure_one()
        active_contracts = self.active_contract_ids
        open_invoices = active_contracts.mapped("open_invoice_ids").filtered(
            lambda i: i.invoice_date_due >= invoicing_date
            and i.invoice_date_due.year == invoicing_date.year
        )

        # invoice already open we complete the move lines
        current_rec_unit_date = getattr(invoicing_date, self.recurring_unit)
        # Keep invoice from the same month or year
        # (depending on the recurring unit)
        open_invoice = open_invoices.filtered(
            lambda m: getattr(m.invoice_date_due, self.recurring_unit)
            == current_rec_unit_date
        )
        if len(open_invoice) > 1:
            raise ValueError(f"Found more than one open invoice on {invoicing_date}.")

        if open_invoice:
            # Retrieve account_move_line already existing for this contract
            acc_move_line_curr_contr = open_invoice.mapped("invoice_line_ids").filtered(
                lambda line: line.contract_id in active_contracts
                and line.product_id
                in active_contracts.mapped("contract_line_ids.product_id")
            )
            move_line_contract_ids = acc_move_line_curr_contr.mapped("contract_id")
            move_line_product_ids = acc_move_line_curr_contr.mapped("product_id")
            already_paid_cl = (
                self.env["account.move.line"]
                .search(
                    [
                        ("date", "=", invoicing_date),
                        ("contract_id", "in", self.active_contract_ids.ids),
                        (
                            "product_id",
                            "in",
                            self.active_contract_ids.mapped("product_ids").ids,
                        ),
                        ("payment_state", "=", "paid"),
                    ]
                )
                .mapped("contract_id.contract_line_ids")
            )
            contract_lines_to_inv = active_contracts.mapped(
                "contract_line_ids"
            ).filtered(
                lambda contract_line: (
                    contract_line.contract_id not in move_line_contract_ids
                    or contract_line.product_id not in move_line_product_ids
                )
                and contract_line not in already_paid_cl
            )
            open_invoice.write(
                {
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            self.build_inv_line_data(
                                invoicing_date=invoicing_date, contract_line=cl
                            ),
                        )
                        for cl in contract_lines_to_inv
                    ],
                    "payment_mode_id": self.payment_mode_id.id,
                }
            )
        else:
            # Building invoices data
            contracts = self.active_contract_ids

            if contract is not None:
                contracts = contract

            inv_data = self._build_invoice_gen_data(invoicing_date, invoicer, contracts)
            # Creating the actual invoice
            _logger.info(f"Generating invoice : {inv_data}")
            invoice = self.env["account.move"].create(inv_data)
            # If the invoice has something to be paid we post it to activate it
            if invoice.invoice_line_ids:
                invoice.action_post()
            else:
                _logger.warning(
                    f"Invoice tried to generate a 0 amount invoice for"
                    f"payment option {self.id}"
                )
                invoice.unlink()

    def _build_invoice_gen_data(
        self, invoicing_date, invoicer, contracts, gift_wizard=False
    ):
        """Setup a dict with data passed to invoice.create.
        If any custom data is wanted in invoice from contract group, just
        inherit this method.
        """
        self.ensure_one()
        # Filter the contract line already paid
        already_paid_cl = (
            self.env["account.move.line"]
            .search(
                [
                    ("date", "=", invoicing_date),
                    ("contract_id", "in", contracts.ids),
                    (
                        "product_id",
                        "in",
                        contracts.mapped("product_ids").ids,
                    ),
                    ("payment_state", "=", "paid"),
                ]
            )
            .mapped("contract_id.contract_line_ids")
        )
        # we use the first contract because the information we retrieve
        # has to be shared between all the contracts of the list
        reference_contract = contracts[0]
        company_id = reference_contract.company_id.id
        partner_id = self._get_partner_for_contract(reference_contract).id
        journal = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", company_id)], limit=1
        )
        inv_data = {
            "payment_reference": self.ref,  # Accountant reference
            "ref": self.ref,  # Internal reference
            "move_type": "out_invoice",
            "partner_id": partner_id,
            "journal_id": journal.id,
            "currency_id": reference_contract.pricelist_id.currency_id.id,
            "invoice_date": invoicing_date,  # Accountant date
            "recurring_invoicer_id": invoicer.id,
            "pricelist_id": reference_contract.pricelist_id.id,
            "payment_mode_id": self.payment_mode_id.id,
            "company_id": company_id,
            # Field for the invoice_due_date to be automatically calculated
            "invoice_payment_term_id": self.partner_id.property_payment_term_id.id
            or self.env.ref("account.account_payment_term_immediate").id,
            "invoice_line_ids": [
                (
                    0,
                    0,
                    self.build_inv_line_data(
                        invoicing_date=invoicing_date,
                        gift_wizard=gift_wizard,
                    ),
                )
            ]
            if gift_wizard
            else [
                (
                    0,
                    0,
                    self.build_inv_line_data(
                        invoicing_date=invoicing_date, contract_line=cl
                    ),
                )
                for cl in (contracts.mapped("contract_line_ids") - already_paid_cl)
                if cl
            ],
            "narration": "\n".join(
                [
                    "" if not comment else comment
                    for comment in self.mapped("active_contract_ids.comment")
                ]
                or ""
            ),
        }
        return inv_data

    def build_inv_line_data(
        self, invoicing_date=False, gift_wizard=False, contract_line=False
    ):
        """
        Set up a dictionary with data passed to
        `self.env['account.move.line'].create({})`.
        :return: a dictionary
        """
        self.ensure_one()
        if contract_line:
            product = contract_line.product_id
            qty = contract_line.quantity
            contract = contract_line.contract_id
            line_name = product.name
            if contract_line.pricelist_item_count:
                price = contract.pricelist_id.get_product_price(
                    product, qty, contract.partner_id, invoicing_date
                )
            else:
                price = contract_line.amount
            if product.pricelist_item_count > 0:
                price = contract.pricelist_id.get_product_price(
                    product, qty, self.partner_id, invoicing_date
                )
        elif gift_wizard:
            product = gift_wizard.product_id
            qty = gift_wizard.quantity
            contract = gift_wizard.contract_id
            price = gift_wizard.amount
            line_name = gift_wizard.description or product.name
        else:
            raise ValueError(
                "This method should get a contract_line or a product and quantity"
            )

        return {
            "name": line_name,
            "price_unit": price,
            "quantity": qty,
            "product_id": product.id,
            "contract_id": contract.id,
            "account_id": product.with_company(
                contract.company_id.id
            ).property_account_income_id.id
            or False,
        }

    def _updt_invoices_cg(self, vals):
        """method to update invoices on contrat group (cg)
        :params vals dict of value that has been modified on the cg
        """
        if any(key in vals for key in ("payment_mode_id", "ref")):
            invoices = self.mapped("active_contract_ids.open_invoice_ids")
            data_invs = invoices._build_invoices_data(
                ref=vals.get("ref"), pay_mode_id=vals.get("payment_mode_id")
            )
            if data_invs:
                invoices.update_open_invoices(data_invs)
        if "advance_billing_months" in vals:
            # In case the advance_billing_months is greater than before
            # we should generate more invoices
            self.active_contract_ids.button_generate_invoices()

    def _get_partner_for_contract(self, contract):
        return contract.partner_id
