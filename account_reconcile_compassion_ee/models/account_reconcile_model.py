from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AccountReconcileModel(models.Model):
    _inherit = "account.reconcile.model"

    partner_matching_ids = fields.One2many(
        "account.reconcile.model.partner.matching", "model_id", "Partner Matching Rules"
    )
    only_this_month = fields.Boolean(
        default=False, help="Check to search only from the start of the month"
    )
    matching_account_id = fields.Many2one("account.account")

    @api.onchange("past_months_limit")
    def _uncheck_only_this_month(self):
        if self.past_months_limit and self.only_this_month:
            self.only_this_month = False

    def _get_partner_from_mapping(self, st_line):
        partner = super()._get_partner_from_mapping(st_line)
        if not partner:
            for matching in self.partner_matching_ids.filtered("is_active"):
                partner = matching.match_line(st_line)
                if partner:
                    return partner
        return partner

    def _get_invoice_matching_amls_domain(self, st_line, partner):
        domain = super()._get_invoice_matching_amls_domain(st_line, partner)
        st_line_date = st_line.date or fields.Date.today()
        if self.past_months_limit:
            # Replace the date filter with the bs_date instead of today's date
            date_limit = st_line_date - relativedelta(months=self.past_months_limit)
            domain = [
                ("date", ">=", fields.Date.to_string(date_limit))
                if filter[0] == "date"
                else filter
                for filter in domain
            ]
        elif self.only_this_month:
            date_start = st_line_date.replace(day=1)
            date_end = date_start + relativedelta(months=1)
            domain.extend(
                [
                    ("date", ">=", fields.Date.to_string(date_start)),
                    ("date", "<", fields.Date.to_string(date_end)),
                ]
            )
        if self.matching_account_id:
            domain.append(("account_id", "=", self.matching_account_id.id))
        return domain
