##############################################################################
#
#    Copyright (C) 2014-2022 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Cyril Sester <csester@compassion.ch>, Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################

import html
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = "account.move"

    last_payment = fields.Date(
        "Paid on", compute="_compute_last_payment", store=True, tracking=True
    )

    def _filter_open_invoices(self):
        """Return the invoices of self that are still open, i.e. not fully paid.

        This is the single definition of "open invoice" used by the stat
        buttons of recurring.contract and recurring.contract.group, so that
        both levels always agree. It matches the criterion used by
        amount_due / months_due (see recurring.contract._filter_due_invoices).

        Not to be confused with recurring.contract.open_invoice_ids, which is
        stricter on purpose: that field drives invoice generation and the write
        cascade, which both reset invoices to draft, and button_draft()
        unreconciles the payments of the invoice.
        """
        return self.filtered(
            lambda i: i.payment_state != "paid" and i.state not in ("cancel", "draft")
        )

    @api.depends("partner_id", "company_id")
    def _compute_pricelist_id(self):
        # Prevent overriding the pricelist_id if it is already set for a new move
        for invoice in self:
            pricelist = invoice.mapped("invoice_line_ids.contract_id.pricelist_id")
            if not invoice.id and invoice.pricelist_id:
                invoice.pricelist_id = invoice.pricelist_id
            elif len(pricelist) == 1:
                invoice.pricelist_id = pricelist
            else:
                super(AccountMove, invoice)._compute_pricelist_id()
        return True

    @api.depends("payment_state", "line_ids.full_reconcile_id", "line_ids.reconciled")
    def _compute_last_payment(self):
        for invoice in self:
            payment_dates = []
            for line in invoice.line_ids:
                if line.reconciled and line.full_reconcile_id:
                    mv_filter = (
                        "credit" if invoice.move_type == "out_invoice" else "debit"
                    )
                    payment_lines = line.full_reconcile_id.reconciled_line_ids.filtered(
                        lambda r, _mv_filter=mv_filter: r[_mv_filter]
                    )
                    # Direct Debit : the payment is not linked
                    # with a bank statement line
                    if not payment_lines.move_id.statement_line_id:
                        # We search for the reconciled
                        # bank statement lines to get the date
                        st_lines = payment_lines.mapped(
                            "move_id.line_ids.full_reconcile_id.reconciled_line_ids"
                            ".statement_line_id"
                        )
                        payment_dates.extend(st_lines.mapped("date"))
                    else:
                        payment_dates.extend(payment_lines.mapped("date"))
            if payment_dates:
                invoice.last_payment = max(payment_dates)
            else:
                invoice.last_payment = False

    def _compute_payments_widget_reconciled_info(self):
        # Add payment date info to the payment widget (for direct debit payments)
        super()._compute_payments_widget_reconciled_info()
        for move in self:
            if move.invoice_payments_widget:
                if move.payment_state in ("paid", "in_payment") and move.is_invoice(
                    include_receipts=True
                ):
                    reconciled_partials = move._get_all_reconciled_invoice_partials()
                    for i, reconciled_partial in enumerate(reconciled_partials):
                        counterpart_line = reconciled_partial["aml"]
                        payment_lines = counterpart_line.mapped(
                            "matched_debit_ids.debit_move_id.payment_line_ids"
                        )
                        if payment_lines:
                            bank_lines = counterpart_line.move_id.line_ids.mapped(
                                "matched_credit_ids.credit_move_id.statement_line_id"
                            )
                            move.invoice_payments_widget["content"][i].update(
                                {
                                    "payment_state": move.payment_state,
                                    "payment_date": max(
                                        (bank_lines or payment_lines).mapped("date")
                                    ),
                                }
                            )
        return True

    def action_register_payment(self):
        """After registering a payment post a message of the bank statement linked"""
        out = super().action_register_payment()
        self.message_post_bank_statement_notes()
        return out

    def message_post_bank_statement_notes(self):
        """Post a message in the invoice with the messages
        of the bank statement related to this invoice"""
        for invoice in self:
            invoice._message_post_bank_statement_notes()

    def _message_post_bank_statement_notes(self):
        notes = self._get_bank_statement_notes()
        if not notes:
            return
        notes_text = "".join(f"<li>{html.escape(note)}</li>" for note in notes)
        self.message_post(
            body=_("Notes from bank statement") + f" : <ul>{notes_text}</ul>"
        )

    def _get_bank_statement_notes(self):
        statement_line_ids = self.mapped(
            "line_ids.full_reconcile_id.reconciled_line_ids.statement_line_id"
        )
        return statement_line_ids.filtered("narration").mapped("narration")

    def reconcile_after_clean(self):
        """
        Called after clean invoices. If invoices can be reconciled
        with open payment, this will do it.
        Invoices should be open when called.
        :return: True
        """
        today = date.today()
        mvl_obj = self.env["account.move.line"]
        for partner in self.mapped("partner_id"):
            invoices = self.filtered(lambda i, p=partner: i.partner_id == p)
            past_invoices = invoices.filtered(lambda i: i.invoice_date <= today)
            past_lines = past_invoices.mapped("line_ids").filtered("debit")
            past_amount = sum(past_invoices.mapped("amount_total"))
            future_invoices = invoices - past_invoices
            future_lines = future_invoices.mapped("line_ids").filtered("debit")
            future_amount = sum(future_invoices.mapped("amount_total"))

            # First try to find matching amount payments
            criterias = [
                ("partner_id", "=", partner.id),
                ("account_id", "=", partner.property_account_receivable_id.id),
                ("reconciled", "=", False),
                ("parent_state", "=", "posted"),
            ]
            open_payments = mvl_obj.search(
                criterias + [("credit", "in", [past_amount, future_amount])]
            )
            for payment in open_payments:
                if past_invoices and payment.credit == past_amount:
                    (past_lines + payment).reconcile()
                    past_invoices = past_invoices.filtered(
                        lambda i: i.payment_state != "paid"
                    )
                    future_invoices = future_invoices.filtered(
                        lambda i: i.payment_state != "paid"
                    )
                    future_amount = sum(future_invoices.mapped("amount_total"))
                elif future_invoices and payment.credit == future_amount:
                    (future_lines + payment).reconcile()
                    future_invoices = future_invoices.filtered(
                        lambda i: i.payment_state != "paid"
                    )

            # If no matching payment found, we will use leftovers with bigger credit.
            if past_invoices:
                past_lines.group_reconcile(mvl_obj.search(criterias))
                future_invoices = future_invoices.filtered(
                    lambda i: i.payment_state != "paid"
                )
            if future_invoices:
                future_lines.group_reconcile(mvl_obj.search(criterias))
        return True

    def update_open_invoices(self, updt_val):
        """
        It updates the invoices in self with the value of updt_val.
        The function acts as a filter to make sure we perform valid updates
        on open invoices in the present or future.

        :param updt_val: a dictionary of invoices values with the invoice name
        which refer to another dictionary of values for that invoice name
        """
        inv_block_day = self.env["res.config.settings"].get_param_multi_company(
            "recurring_contract.invoice_block_day"
        )
        # Filter out past invoices.
        date_selection = date.today()
        if inv_block_day and date_selection.day >= int(inv_block_day):
            date_selection += relativedelta(months=1)
        date_selection = date_selection.replace(day=1)
        for invoice in self.filtered(
            lambda i: i.state != "cancel"
            and i.payment_state != "paid"
            and (i.invoice_date or i.date) >= date_selection
            and (
                i.payment_order_id.state in ["draft", "open"] or not i.payment_order_id
            )
        ):
            if updt_val.get(invoice.name):
                val_to_updt = updt_val[invoice.name]
                if (
                    "partner_id" in val_to_updt
                    and val_to_updt["partner_id"] == invoice.partner_id.id
                ):
                    del val_to_updt["partner_id"]
                    if not val_to_updt:
                        continue
                # In case we modify the amount we want to test if the amount is zero
                invoice.button_draft()
                invoice.update(val_to_updt)
                if invoice.amount_total:
                    invoice.action_post()
                else:
                    invoice.button_cancel()

    def _build_invoices_data(
        self,
        contracts=False,
        invoice_date=False,
        ref=False,
        pay_mode_id=False,
        payment_term_id=False,
        partner_id=False,
    ):
        """
        Returns a dictionary for creating invoices given the few parameters.

        :param contracts: recurring_contract for which we generate lines (optional)
        :param invoice_date: The date of the invoice, (optional)
        :param ref: The reference of the invoice, defaults to False (optional)
        :param pay_mode_id: The payment mode to be used for the invoice (optional)
        :param payment_term_id: payment term id to use. (optional)
        :param partner_id: force the partner to use (optional)
        :return: A dictionary with the invoice_line_ids, date, payment_reference,
                 and payment_mode_id.
        """
        res = {}
        for invoice in self:
            inv_val_dict = {}
            if contracts:
                inv_val_dict["invoice_line_ids"] = (
                    invoice._build_invoice_lines_from_contracts(contracts)
                )
                # Special case for payment_mode: it needs always to be there,
                # otherwise a compute method overrides it.
                if not pay_mode_id:
                    pay_mode_id = contracts.mapped("group_id.payment_mode_id")[:1].id
            if invoice_date:
                inv_val_dict["date"] = invoice_date
            if payment_term_id:
                inv_val_dict["invoice_payment_term_id"] = payment_term_id
            if partner_id:
                inv_val_dict["partner_id"] = partner_id
            if ref:
                inv_val_dict["payment_reference"] = ref
                inv_val_dict["ref"] = ref
            if pay_mode_id:
                inv_val_dict["payment_mode_id"] = pay_mode_id
            if inv_val_dict:
                res[invoice.name] = inv_val_dict
        return res

    def _build_invoice_lines_from_contracts(self, modified_contracts):
        """
        It creates a list of tuples that will be used to create,
        modify or delete invoice lines, given information from contracts.

        :param modified_contracts: <recurring.contract> recordset.
        """
        self.ensure_one()
        res = []
        for contract in modified_contracts.filtered(
            lambda c: c.start_date
            and c.start_date.date() < (self.invoice_date or self.date)
        ):
            invoice_lines = self.invoice_line_ids.filtered(
                lambda invoice_line, c=contract: invoice_line.contract_id == c
            )
            contract_products = contract.product_ids
            invoice_products = invoice_lines.mapped("product_id")
            missing_contract_lines = contract.contract_line_ids.filtered(
                lambda cl, cp=contract_products, invp=invoice_products: cl.product_id
                in cp
                and cl.product_id not in invp
            )
            obsolete_lines = invoice_lines.filtered(
                lambda invl, cp=contract_products: invl.product_id not in cp
            )
            lines_to_update = invoice_lines - obsolete_lines

            # Add new contract lines in invoices
            res.extend(
                [
                    (0, 0, contract_line.build_inv_line_data())
                    for contract_line in missing_contract_lines
                ]
            )
            # Remove old contract lines
            res.extend([(2, line.id, 0) for line in obsolete_lines])
            # Update other lines
            res.extend(lines_to_update._update_invoice_lines_from_contract(contract))
        return res
