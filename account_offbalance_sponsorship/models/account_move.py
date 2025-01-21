##############################################################################
#
#    Copyright (C) 2014-today Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: David Wulliamoz <dwulliamoz@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def js_remove_outstanding_partial(self, partial_id):
        """Called by the 'payment' widget to remove a reconciled entry to the present
        invoice.

        :param partial_id: The id of an existing partial reconciled with the current
        invoice.
        """
        mv = self.env["account.partial.reconcile"].browse(partial_id)
        mv.debit_move_id.remove_off_balance_lines(mv.debit_move_id.move_id, self)
        res = super().js_remove_outstanding_partial(partial_id)
        return res


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def get_account_offbalance(self, company):
        param_obj = self.env["res.config.settings"].with_company(company)
        return (
            param_obj.get_param("account_offbalance_receivable"),
            param_obj.get_param("account_offbalance_asset"),
        )

    def reconcile(self):
        # check if there is a currency diff
        # and reload the invoice with the rate received
        filtered_item = self.filtered(
            lambda line: line.journal_id != self.company_id.currency_exchange_journal_id
        )
        total = total_curr = 0
        for line in filtered_item:
            total = line.debit - line.credit + total
            total_curr = line.amount_currency + total_curr
        if total != 0 and total_curr == 0:
            inv_to_refresh = filtered_item.filtered(
                lambda line: line.move_id.journal_id.type == "sale"
            ).move_id
            nr = filtered_item.filtered(
                lambda line: line.move_id.journal_id.type != "sale"
            )
            new_rate = sum(n.amount_currency for n in nr) / sum(
                n.debit - n.credit for n in nr
            )
            inv_to_refresh.button_draft()
            for line in inv_to_refresh.line_ids.with_context(check_move_validity=False):
                line.debit = (
                    abs(line.amount_currency / new_rate)
                    if line.amount_currency > 0
                    else 0
                )
                line.credit = (
                    abs(line.amount_currency / new_rate)
                    if line.amount_currency < 0
                    else 0
                )
            inv_to_refresh.action_post()
        # reconcile
        res = super().reconcile()
        # check if the reconcile is regarding off balance moves
        (
            account_offbalance_receivable,
            account_offbalance_asset,
        ) = self.get_account_offbalance(self[0].move_id.company_id)
        if self[0].account_id.id == account_offbalance_receivable:
            if "partials" in res.keys():
                for part in res["partials"]:
                    self.add_off_balance_lines(
                        part,
                        account_offbalance_receivable,
                        account_offbalance_asset,
                        self[0].move_id.company_id,
                    )
                return res

    def remove_off_balance_lines(self, inv_move, pmt_move):
        rec_lines = pmt_move.line_ids
        off_rec, off_ass = rec_lines.get_account_offbalance(inv_move.company_id)
        if rec_lines.filtered(lambda r: r.account_id.id == off_rec):
            for pmt in pmt_move:
                pmt.with_context(skip_account_move_synchronization=True).write(
                    {"state": "draft"}
                )
                ids_to_unlink = self.env["account.move.line"]
                for move_name in inv_move.mapped("name"):
                    ids_to_unlink += rec_lines.filtered(
                        lambda line, current_name=move_name: line.account_id.id
                        != off_rec
                        and line.name == current_name
                    )
                pmt.line_ids -= ids_to_unlink
                pmt.write({"state": "posted"})

        return True

    def add_off_balance_lines(
        self, mv, account_offbalance_receivable, account_offbalance_asset, company
    ):
        rec_invoice_line_ids = mv.debit_move_id.move_id.line_ids.filtered(
            lambda mvl: mvl.account_id.code.startswith("93")
        )
        counterpart_credit_amount = sum(
            inv_line.credit for inv_line in rec_invoice_line_ids
        )
        # Only allocate as income what has been "closed"
        pmt_move = mv.credit_move_id.move_id
        pmt_move_receivable_amount = sum(
            mvl.credit - mvl.debit
            for mvl in pmt_move.line_ids.filtered(
                lambda a: a.account_id.id == account_offbalance_receivable
            )
        )
        closed_amount = (
            mv.amount
            if mv.amount < pmt_move_receivable_amount
            else pmt_move_receivable_amount
        )
        add_lines = (
            self.env["account.move.line"]
            .with_context(check_move_validity=False)
            .create(
                {
                    "account_id": account_offbalance_asset,
                    "name": mv.debit_move_id.move_id.name,
                    "move_id": pmt_move.id,
                    "partner_id": pmt_move.partner_id.id,
                    "debit": closed_amount,
                    "credit": 0,
                }
            )
        )
        total_amount_lines = 0
        for inv_line in rec_invoice_line_ids:
            inc_acc = self.env["account.account"].search(
                [
                    ("code", "=", inv_line.account_id.code[1:]),
                    ("company_id", "=", company.id),
                ]
            )
            amount_line = round(
                closed_amount / counterpart_credit_amount * inv_line.credit, 2
            )
            if abs(closed_amount - total_amount_lines - amount_line) <= 0.1:
                # to avoid rounding issues
                amount_line = closed_amount - total_amount_lines
            else:
                total_amount_lines += amount_line
            add_lines += (
                self.env["account.move.line"]
                .with_context(check_move_validity=False)
                .create(
                    {
                        "account_id": inc_acc.id,
                        "move_id": pmt_move.id,
                        "debit": 0,
                        "name": mv.debit_move_id.move_id.name,
                        "product_id": inv_line.product_id.id,
                        "partner_id": inv_line.partner_id.id,
                        "credit": amount_line,
                    }
                )
            )
        pmt_move.line_ids += add_lines

    def remove_move_reconcile(self):
        """Undo a reconciliation"""
        if not self._context.get("bypass_offbalance_operations"):
            inv_move = (
                self.matched_debit_ids.debit_move_id.move_id
                + self.matched_credit_ids.debit_move_id.move_id
            )
            pmt_move = (
                self.matched_credit_ids.credit_move_id.move_id
                + self.matched_debit_ids.credit_move_id.move_id
            )
            self.remove_off_balance_lines(inv_move, pmt_move)
        super().remove_move_reconcile()
