import os

from odoo import _, fields, models
from odoo.modules.module import get_module_root
from odoo.addons.base.models.res_bank import sanitize_account_number

class EbillPostfinanceInvoiceMessage(models.Model):
    _inherit = "ebill.postfinance.invoice.message"

    grouped_invoices = fields.Many2many(
        comodel_name="account.move",
        string="Invoices linked to this eBill",
    )

    def _get_template_yb(self, jinja_env):
        if self.invoice_id:
            return super(EbillPostfinanceInvoiceMessage, self)._get_template_yb(jinja_env)
        invoice_template_yb = "invoice-yellowbill-installments.jinja"
        return jinja_env.get_template(invoice_template_yb)

    def _generate_payload_yb(self):
        """Generates the xml in the yellowbill format."""
        if self.invoice_id:
            return super(EbillPostfinanceInvoiceMessage, self)._generate_payload_yb()
        else:
            template_dir = [get_module_root(os.path.dirname(__file__)) + "/messages"]
            params = self._get_payload_params_yb()
            jinja_env = self._get_jinja_env(template_dir)
            jinja_template = self._get_template_yb(jinja_env)
            return jinja_template.render(params)

    def _get_payload_params_yb(self):
        if self.invoice_id:
            return super(EbillPostfinanceInvoiceMessage, self)._get_payload_params_yb()
        else:
            partner_bank_id = self.grouped_invoices[0].partner_bank_id if len(self.grouped_invoices) > 0 else False
            partner_shipping_id = self.grouped_invoices[0].partner_shipping_id if len(self.grouped_invoices) > 0 else False
            partner_id = self.grouped_invoices[0].partner_id if len(self.grouped_invoices) > 0 else False

            company_id = self.grouped_invoices[0].company_id if len(self.grouped_invoices) > 0 else False
            move_type = self.grouped_invoices[0].move_type if len(self.grouped_invoices) > 0 else False
            amount_by_group = self.grouped_invoices[0].amount_by_group if len(self.grouped_invoices) > 0 else False
            payment_reference = self.grouped_invoices[0].payment_reference if len(self.grouped_invoices) > 0 else False
            min_date_invoice = min([inv.invoice_date for inv in self.grouped_invoices])
            currency_id = self.grouped_invoices[0].currency_id if len(self.grouped_invoices) > 0 else False
            document_type = {"out_invoice": "EFD", "out_refund": "EGS"}

            # We use the first invoice name followed by '-group' for the group_name name
            group_name = self.grouped_invoices[0].name + "-group" if len(self.grouped_invoices) > 0 else False

            if self.payment_type == "iban":
                bank_account = sanitize_account_number(
                    partner_bank_id.l10n_ch_qr_iban
                    or partner_bank_id.acc_number
                )
            else:
                bank_account = partner_bank_id.l10n_ch_isr_subscription_chf
                if bank_account:
                    account_parts = bank_account.split("-")
                    bank_account = (
                        account_parts[0] + account_parts[1].rjust(6, "0") + account_parts[2]
                    )
                else:
                    bank_account = ""

            delivery = (
                partner_shipping_id
                if partner_shipping_id!= partner_id
                else False
            )
            orders = self.grouped_invoices.line_ids.sale_line_ids.mapped("order_id")
            params = {
                "date_invoice": min_date_invoice,
                "group_name": group_name,
                "payment_reference": payment_reference,
                "amount_total": sum([inv.amount_total if inv.amount_total else 0 for inv in self.grouped_invoices]),
                "amount_untaxed" : sum([inv.amount_untaxed if inv.amount_untaxed else 0 for inv in self.grouped_invoices]),
                "amount_tax": sum([inv.amount_tax if inv.amount_tax else 0 for inv in self.grouped_invoices]),
                "saleorder": orders,
                "currency_id": currency_id,
                "message": self,
                "client_pid": self.service_id.biller_id,
                "invoice_lines": self.grouped_invoices.invoice_line_ids.filtered(lambda r: not r.display_type),
                "grouped_invoices": self.grouped_invoices,
                "lines_by_invoice": {inv:inv.postfinance_invoice_line_ids() for inv in self.grouped_invoices},
                "payment_reference" : self.grouped_invoices[0].payment_reference,
                "biller": company_id,
                "move_type":move_type,
                "customer": partner_id,
                "delivery": delivery,
                "pdf_data": self.attachment_id.datas.decode("ascii"),
                "bank": partner_bank_id,
                "bank_account": bank_account,
                "transaction_id": self.transaction_id,
                "payment_type": self.payment_type,
                "amount_sign": -1 if self.payment_type == "credit" else 1,
                "document_type": document_type[move_type],
                "format_date": self.format_date_yb,
                "ebill_account_number": self.ebill_account_number,
                "discount_template": "",
                "discount": {},
                "invoice_line_stock_template": "",
            }
            final_amount_by_group = []
            # Get the percentage of the tax from the name of the group
            # Could be improve by searching in the account_tax linked to the group
            for taxgroup in amount_by_group:
                rate = taxgroup[0].split()[-1:][0][:-1]
                final_amount_by_group.append(
                    (
                        rate or "0",
                        taxgroup[1],
                        taxgroup[2],
                    )
                )
            params["amount_by_group"] = final_amount_by_group
            # Get the invoice due date
            data_due_by_invoice = {}
            for inv in self.grouped_invoices:
                date_due = inv.invoice_date_due
                if not date_due:
                    if inv.invoice_payment_term_id:
                        terms = inv.invoice_payment_term_id.compute(
                            inv.amount_total
                        )
                        if terms:
                            # Get the last payment date
                            date_due = terms[-1][0]
                    if not date_due:
                        date_due = self.format_date_yb(
                            inv.invoice_date_due or inv.invoice_date
                        )
                data_due_by_invoice[inv] = date_due
            params["date_due_by_invoice"] = data_due_by_invoice
            params["first_due_date"] = min([data_due_by_invoice[i] for i in data_due_by_invoice])
            return params

    def set_transaction_id(self):
        self.ensure_one()
        if self.invoice_id:
            super(EbillPostfinanceInvoiceMessage, self).set_transaction_id()
        else:
            # We use the first invoice name followed by '-group' for the transaction_id
            name = self.grouped_invoices[0].name + "-group" if len(self.grouped_invoices) > 0 else False
            self.transaction_id = "-".join(
                [
                    fields.Datetime.now().strftime("%y%m%d%H%M%S"),
                    name.replace("/", "").replace("_", ""),
                ]
            )
