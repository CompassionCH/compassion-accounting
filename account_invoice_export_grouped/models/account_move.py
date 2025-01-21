# Copyright 2020 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


import odoo
from odoo import _, models
from odoo.exceptions import UserError, except_orm


class AccountMove(models.Model):
    _inherit = "account.move"

    def export_invoice_as_installment(self):
        resend_invoice = self.env.context.get("resend_ebill", False)
        self.with_context(grouped_invoices=True)
        self.env.context.get("grouped_invoices")
        for partner in self.partner_id:
            invoices = self.filtered(lambda move: move.partner_id.id == partner.id)
            invoices._job_export_invoice_grouped(True)

    def _invoices_can_be_grouped_on_ebill(self, raiseError=False):
        # The necessary conditions for the invoices to be grouped are the following:
        # 1) The partner_id should be the same
        # 2) The partner_bank_id should be the same
        # 3) The partner_shipping_id should be the same
        # 4) The company_id should be the same
        # 5) The move_type should be the same
        # 6) The amount_by_group should be the same
        # 7) The currency_id should be the same
        if len(self.partner_id) > 1:
            if raiseError:
                raise UserError(
                    "The invoices cannot be grouped as they are not all for the same partner"
                )
            return False
        if len(self.partner_bank_id) > 1:
            if raiseError:
                raise UserError(
                    "The invoices cannot be grouped as they are not all for the same bank"
                )
            return False
        if len(self.partner_shipping_id) > 1:
            if raiseError:
                raise UserError(
                    "The invoices cannot be grouped as they have not the same shipping id"
                )
            return False
        if len(self.company_id) > 1:
            if raiseError:
                raise UserError(
                    "The invoices cannot be grouped as they have not the same company id"
                )
            return False
        if len({inv.move_type for inv in self}) > 1:
            if raiseError:
                raise UserError(
                    "The invoices cannot be grouped as they have not the same move type"
                )
            return False
        if len({len(inv.amount_by_group) for inv in self}) > 1:
            if raiseError:
                raise UserError(
                    "The invoices cannot be grouped as they have not the same amount_by_group"
                )
            return False
        if len(self.currency_id) > 1:
            if raiseError:
                raise UserError(
                    "The invoices cannot be grouped as they don't have the same currency"
                )
            return False
        return True

    def _job_export_invoice_grouped(self, resend_invoice=False):
        """Export ebill to external server and update the chatter."""
        if self._invoices_can_be_grouped_on_ebill(True):
            if not resend_invoice:
                return _("Nothing done, invoice has already been exported before.")
            try:
                res = self._export_invoice_grouped()
            except Exception as e:
                values = {
                    "job_id": self.env.context.get("job_uuid"),
                    "error_detail": "",
                    "error_type": type(e).__name__,
                    "transmit_method_name": self.transmit_method_id.name,
                }
                if isinstance(e, except_orm):
                    values["error_detail"] = e.name
                with odoo.api.Environment.manage():
                    with odoo.registry(self.env.cr.dbname).cursor() as new_cr:
                        # Create a new environment with new cursor database
                        new_env = odoo.api.Environment(
                            new_cr, self.env.uid, self.env.context
                        )
                        # The chatter of the invoice need to be updated, when the job fails
                        self.with_env(new_env).log_error_sending_invoice(values)
                raise
            for invoice in self:
                invoice.log_success_sending_invoice()
            return res
        return False

    def create_postfinance_ebill_grouped(self):
        message = None
        if len(self) > 0:
            message = super(AccountMove, self[0]).create_postfinance_ebill()
            message.invoice_id = False
            message.grouped_invoices = self
        return message

    def _export_invoice_grouped(self):
        if len(self) == 1:
            return super(AccountMove, self)._export_invoice()
        else:
            """Export invoice with the help of account_invoice_export module."""
            postfinance_method = self.env.ref(
                "ebill_postfinance.postfinance_transmit_method"
            )
            if self.transmit_method_id != postfinance_method:
                return super()._export_invoice()
            message = self.create_postfinance_ebill_grouped()
            if not message:
                raise UserError(_("Error generating postfinance eBill"))
            message.send_to_postfinance()
            self.invoice_exported = True
            return "Postfinance invoice generated and in state {}".format(message.state)
