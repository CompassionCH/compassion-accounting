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

    last_payment = fields.Date(compute="_compute_last_payment", store=True)
    recurring_invoicer_id = fields.Many2one(
        "recurring.invoicer", "Invoicer", readonly=False
    )

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
                    payment_dates.extend(payment_lines.mapped("date"))
            if payment_dates:
                invoice.last_payment = max(payment_dates)
            else:
                invoice.last_payment = False

    def register_payment(
        self, payment_line, writeoff_acc_id=False, writeoff_journal_id=False
    ):
        """After registering a payment post a message of the bank statement linked"""
        out = super().register_payment(
            payment_line, writeoff_acc_id, writeoff_journal_id
        )
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

    def action_invoice_paid(self):
        """Call invoice_paid method on related contracts."""
        res = super().action_invoice_paid()
        for invoice in self:
            contracts = invoice.mapped("invoice_line_ids.contract_id")
            contracts.invoice_paid(invoice)
        return res

    def action_invoice_re_open(self):
        """Call invoice_unpaid method on related contract."""
        res = super().action_invoice_re_open()
        for invoice in self:
            contracts = invoice.mapped("invoice_line_ids.contract_id")
            contracts.invoice_unpaid(invoice)
        return res

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
            past_invoices = invoices.filtered(lambda i: i.invoice_date_due <= today)
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
            and i.invoice_date_due >= date_selection
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
                inv_val_dict[
                    "invoice_line_ids"
                ] = invoice._build_invoice_lines_from_contracts(contracts)
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
            lambda c: c.start_date.date() < self.invoice_date_due
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
