import re

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

YEAR_TOKEN = re.compile(r"(19|20)\d{2}")


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

    def _get_invoice_matching_st_line_tokens(self, st_line):
        # T3677 A year in the payer's message ("Spende 2026") is not a
        # reference: it would match every invoice whose customer reference
        # names a period of that year ("Periode: Oktober 2026.").
        numerical_tokens, exact_tokens, text_tokens = (
            super()._get_invoice_matching_st_line_tokens(st_line)
        )
        numerical_tokens = [
            token for token in numerical_tokens if not YEAR_TOKEN.fullmatch(token)
        ]
        return numerical_tokens, exact_tokens, text_tokens

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

    def _get_invoice_matching_rules_map(self):
        rules_map = super()._get_invoice_matching_rules_map()
        if not (
            self.match_text_location_label
            or self.match_text_location_note
            or self.match_text_location_reference
        ):
            rules_map[10] = [
                self._get_invoice_matching_proposal_candidates
                if rule == self._get_invoice_matching_amls_candidates
                else rule
                for rule in rules_map[10]
            ]
        return rules_map

    def _get_invoice_matching_proposal_candidates(self, st_line, partner):
        """T3692 Without Label/Note/Reference option, the rule proposes the
        payer's open items whatever their reference or amount. Propose
        nothing for a gift QR payment (its reference never matches an
        invoice: the gift invoice is created at reconcile, so the gift button
        is prefilled instead), and otherwise only an open item of the same
        amount as the payment."""
        if st_line._get_gift_reference():
            return None
        result = self._get_invoice_matching_amls_candidates(st_line, partner)
        if not result or not result.get("amls"):
            return result
        amls = result["amls"].filtered(
            lambda aml: self._is_same_open_amount(st_line, aml)
        )
        if not amls:
            return None
        return {**result, "amls": amls}

    def _is_same_open_amount(self, st_line, aml):
        st_line_currency = st_line.foreign_currency_id or st_line.currency_id
        if aml.currency_id != st_line_currency:
            return False
        st_line_amount = st_line._prepare_move_line_default_vals()[1]["amount_currency"]
        return (
            st_line_currency.compare_amounts(
                st_line_amount, -aml.amount_residual_currency
            )
            == 0
        )
