##############################################################################
#
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################

from odoo import api, fields, models


class SplitInvoiceWizard(models.TransientModel):
    """Wizard for selecting invoice lines to be moved
    onto a new invoice."""

    _name = "account.invoice.split.wizard"
    _description = "Split Invoice Wizard"

    move_id = fields.Many2one(
        "account.move", default=lambda self: self._get_invoice(), readonly=False
    )

    invoice_line_ids = fields.Many2many(
        "account.move.line",
        "account_invoice_line_2_splitwizard",
        "account_invoice_split_wizard_id",
        "account_invoice_line_id",
        string="Invoice lines",
        readonly=False,
    )

    @api.model
    def _get_invoice(self):
        return self.env.context.get("active_id")

    def split_invoice(self):
        self.ensure_one()
        invoice = False

        if self.invoice_line_ids:
            # Get Receivable line
            move_ids = self.invoice_line_ids.mapped("move_id").ids
            all_lines = self.env["account.move.line"].search(
                [("move_id", "in", move_ids)]
            )
            old_receivable_line = all_lines.filtered(
                lambda line: line.account_id.internal_type == "receivable"
            )

            # Compute debit val for old/new Receivable line
            amount_total_new_receivable = 0.0
            for price_tmp in self.invoice_line_ids:
                amount_total_new_receivable += price_tmp.price_total
            amount_total_old_receivable = (
                old_receivable_line.price_unit + amount_total_new_receivable
            )

            # Get old invoice and copy it for new invoice
            old_invoice = self.invoice_line_ids[0].move_id
            if old_invoice.state in ("draft", "posted"):
                invoice = self._copy_invoice(old_invoice)

                # Create new Receivable line for the new invoice
                tmp = (
                    self.env["account.move.line"]
                    .with_context(check_move_validity=False)
                    .create(
                        {
                            "price_unit": -amount_total_new_receivable,
                            "move_id": invoice.id,
                            "quantity": 1,
                            "exclude_from_invoice_tab": True,
                            "account_id": old_receivable_line.account_id.id,
                        }
                    )
                )

                # Set new invoices lines with correct IDs from new invoice
                self.invoice_line_ids = self.invoice_line_ids + tmp
                was_open = old_invoice.state == "posted"
                if was_open:
                    old_invoice.button_draft()
                    old_invoice.env.clear()
                self.invoice_line_ids.write({"move_id": invoice.id})

                # Update old invoice receivable line
                old_receivable_line.write({"price_unit": amount_total_old_receivable})
                if was_open:
                    old_invoice.action_post()
                    invoice.action_post()

        return invoice

    def _copy_invoice(self, old_invoice):
        # Create new invoice
        new_invoice = old_invoice.copy(
            default={"invoice_date": old_invoice.invoice_date}
        )
        new_invoice.line_ids.unlink()
        new_invoice.invoice_line_ids.unlink()
        return new_invoice
