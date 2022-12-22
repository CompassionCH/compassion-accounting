##############################################################################
#
#    Copyright (C) 2014-2022 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, models, fields, exceptions, _


class MoveLine(models.Model):
    """ Adds a method to split a payment into several move_lines
    in order to reconcile only a partial amount, avoiding doing
    partial reconciliation. """

    _inherit = "account.move.line"

    contract_id = fields.Many2one('recurring.contract', 'Source contract', index=True)
    due_date = fields.Date(related='move_id.invoice_date_due', store=True, readonly=True, index=True)
    state = fields.Selection(related="move_id.state")
    last_payment = fields.Date(related="move_id.last_payment", store=True)
    payment_state = fields.Selection(related="move_id.payment_state", store=True, readonly=True, index=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        # workaround an odoo bug :
        # could be fixed by applying this change here
        # - self.analytic_tag_ids = rec.analytic_tag_ids.ids
        # + self.analytic_tag_ids = rec.analytic_tag_ids
        # https://github.com/odoo/odoo/blame/12.0/addons/account_analytic_default/models/account_analytic_default.py#L100
        self.analytic_tag_ids = self.env["account.analytic.tag"]
        res = super()._onchange_product_id()
        return res

    def split_payment_and_reconcile(self):
        sum_credit = sum(self.mapped("credit"))
        sum_debit = sum(self.mapped("debit"))
        if sum_credit == sum_debit:
            # Nothing to do here
            return self.reconcile()

        # Check in which direction we are reconciling
        split_column = "credit" if sum_credit > sum_debit else "debit"
        difference = abs(sum_credit - sum_debit)

        for line in self:
            if getattr(line, split_column) > difference:
                # We will split this line
                move = line.move_id
                move_line = line
                break
        else:
            raise exceptions.UserError(
                _(
                    "This can only be done if one move line can be split "
                    "to cover the reconcile difference"
                )
            )

        # Edit move in order to split payment into two move lines
        payment = move_line.payment_id
        if payment:
            payment_lines = payment.move_line_ids
            payment.move_line_ids = False
        move.button_draft()
        move.write(
            {
                "line_ids": [
                    (1, move_line.id, {split_column: move_line.credit - difference}),
                    (
                        0,
                        0,
                        {
                            split_column: difference,
                            "name": self.env.context.get(
                                "residual_comment", move_line.name
                            ),
                            "account_id": move_line.account_id.id,
                            "date": move_line.date,
                            "date_maturity": move_line.date_maturity,
                            "journal_id": move_line.journal_id.id,
                            "partner_id": move_line.partner_id.id,
                        },
                    ),
                ]
            }
        )
        move.action_post()
        if payment:
            payment.move_line_ids = payment_lines

        # Perform the reconciliation
        return self.reconcile()
