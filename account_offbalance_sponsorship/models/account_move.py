# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014-today Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: David Wulliamoz <dwulliamoz@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import _, models

class AccountMove(models.Model):
    _inherit = "account.move"
    def js_remove_outstanding_partial(self, partial_id):
        ''' Called by the 'payment' widget to remove a reconciled entry to the present invoice.

        :param partial_id: The id of an existing partial reconciled with the current invoice.
        '''
        mv = self.env["account.partial.reconcile"].browse(partial_id)
        account_offbalance_receivable, account_offbalance_asset = self.line_ids.get_account_offbalance(mv.company_id)
        pmt_move = mv.credit_move_id.move_id
        rem_lines = self.env["account.move.line"].search([
            ("account_id", "=", account_offbalance_asset), ("move_id", "=", pmt_move.id),
            ("debit", "=", mv.amount)])
        if rem_lines.statement_line_id:
            rem_lines.statement_line_id.with_delay().button_undo_reconciliation()
        res = super().js_remove_outstanding_partial(partial_id)
        return res

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def get_account_offbalance(self,company):
        param_obj = self.env["res.config.settings"].with_company(company)
        return (param_obj.get_param("account_offbalance_receivable"),param_obj.get_param("account_offbalance_asset"))

    def reconcile(self):
        res = super().reconcile()
        account_offbalance_receivable,account_offbalance_asset = self.get_account_offbalance(self[0].move_id.company_id)
        if self[0].account_id.id == account_offbalance_receivable:
            if "partials" in res.keys():
                for part in res["partials"]:
                    self.add_off_balance_lines(part,account_offbalance_receivable,account_offbalance_asset,self[0].move_id.company_id)
                return res

    def add_off_balance_lines(self,mv,account_offbalance_receivable,account_offbalance_asset,company):
        rec_invoice_line_ids = mv.debit_move_id.move_id.line_ids.filtered(
            lambda l: l.account_id.code.startswith('93'))
        counterpart_credit_amount = sum(inv_line.credit for inv_line in rec_invoice_line_ids)
        # Only allocate as income what has been "closed"
        pmt_move = mv.credit_move_id.move_id
        pmt_move_receivable_amount = sum(l.credit - l.debit for l in pmt_move.line_ids.filtered(lambda a: a.account_id.id == account_offbalance_receivable))
        closed_amount = mv.amount if mv.amount<pmt_move_receivable_amount else pmt_move_receivable_amount
        add_lines = self.env["account.move.line"].with_context(check_move_validity=False).create(
            {"account_id": account_offbalance_asset, "move_id": pmt_move.id, "debit": closed_amount,"credit": 0})
        total_amount_lines = 0
        for inv_line in rec_invoice_line_ids:
            inc_acc = self.env['account.account'].search(
                [('code', '=', inv_line.account_id.code[1:]), ('company_id', '=', company.id)])
            amount_line = round(closed_amount / counterpart_credit_amount * inv_line.credit, 2)
            if abs(closed_amount - total_amount_lines - amount_line) <= .1:
                #to avoid rounding issues
                amount_line = closed_amount - total_amount_lines
            else:
                total_amount_lines += amount_line
            add_lines += self.env["account.move.line"].with_context(check_move_validity=False).create(
                {"account_id": inc_acc.id, "move_id": pmt_move.id, "debit": 0,"product_id": inv_line.product_id.id,
                 "partner_id": inv_line.partner_id.id, "credit": amount_line})
        pmt_move.line_ids += add_lines

    def remove_move_reconcile(self):
        """ Undo a reconciliation """
        if self.move_id:
            part = self.matched_debit_ids + self.matched_credit_ids
            account_offbalance_receivable, account_offbalance_asset = self.get_account_offbalance(
                self[0].move_id.company_id)
            if part and (part[0].debit_move_id.account_id.id == account_offbalance_receivable):
                for mv in part:
                    rec_invoice_line_ids = mv.debit_move_id.move_id.line_ids.filtered(
                        lambda l: l.account_id.code.startswith('93'))
                    counterpart_credit_amount = sum(inv_line.credit for inv_line in rec_invoice_line_ids)
                    closed_amount = mv.amount
                    pmt_move = mv.credit_move_id.move_id
                    rem_lines = self.env["account.move.line"].search([
                        ("account_id","=", account_offbalance_asset),("move_id","=", pmt_move.id), ("debit","=",closed_amount)])
                    if self.filtered(lambda s: s.statement_line_id is not False):
                        rem_lines.statement_line_id.with_delay().button_undo_reconciliation()
                    else:
                        total_amount_lines = 0
                        for inv_line in rec_invoice_line_ids:
                            inc_acc = self.env['account.account'].search(
                                [('code', '=', inv_line.account_id.code[1:]), ('company_id', '=', self.company_id.id)])
                            amount_line = round(closed_amount / counterpart_credit_amount * inv_line.credit, 2)
                            if abs(counterpart_credit_amount - total_amount_lines - amount_line) < 0.1:
                                #to avoid rounding issues
                                amount_line = closed_amount - total_amount_lines
                            else:
                                total_amount_lines += amount_line
                            rem_lines += self.env["account.move.line"].search([
                                ("account_id","=",inc_acc.id),("move_id","=",pmt_move.id),("product_id","=", inv_line.product_id.id)
                                ,("partner_id","=", inv_line.partner_id.id),("credit","=", amount_line)])
                        pmt_move.write({'state': 'draft', 'is_move_sent': False})
                        pmt_move.line_ids -= rem_lines
                        pmt_move.action_post()
        super().remove_move_reconcile()
