from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AccountReconcileModel(models.Model):
    _inherit = "account.reconcile.model"

    partner_matching_ids = fields.One2many(
        "account.reconcile.model.partner.matching",
        "model_id",
        "Partner Matching Rules",
        copy=True,
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
                if isinstance(item, tuple | list) and item and item[0] == "date"
                else item
                for item in domain
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
        if partner and self.env.context.get("match_commercial_partner"):
            # T3677 Look for the open items of the company and all its contacts
            domain = [
                ("partner_id", "child_of", partner.commercial_partner_id.id)
                if item == ("partner_id", "=", partner.id)
                else item
                for item in domain
            ]
        return domain

    def _get_invoice_matching_amls_candidates(self, st_line, partner):
        # T3677 A payment made by a contact can pay an item of its company
        # or of another contact of the company, when its reference matches.
        # Without a matching reference, the proposals stay on the exact partner.
        commercial_partner = partner.commercial_partner_id
        if partner and (commercial_partner != partner or partner.child_ids):
            result = super(
                AccountReconcileModel,
                self.with_context(match_commercial_partner=True),
            )._get_invoice_matching_amls_candidates(st_line, partner)
            if result and result.get("allow_auto_reconcile"):
                result["amls"] = result["amls"].with_env(self.env)
                return result
        return super()._get_invoice_matching_amls_candidates(st_line, partner)

    def _get_invoice_matching_amls_result(self, st_line, partner, candidate_vals):
        result = super()._get_invoice_matching_amls_result(
            st_line, partner, candidate_vals
        )
        # T2665 Nordic team would always like auto reconciliation to happen
        if (
            result is not None
            and self.auto_reconcile
            and self.rule_type == "invoice_matching"
        ):
            result["auto_reconcile"] = True
        return result
