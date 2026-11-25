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
    # T3622 Rules driven by the QR reference of the bank line
    qr_type_ids = fields.Many2many(
        "account.reconcile.qr.type",
        string="QR reference types",
        help="The rule only applies to bank lines whose QR reference is of one "
        "of these types, whose partner exists, and for which a product is found "
        "(gift of the sponsorship, fund...). The counterpart is booked with the "
        "button of the product, or on its income account.",
    )
    match_exact_reference = fields.Boolean(
        "Exact QR reference",
        help="When the bank line has a QR reference, only take the open items "
        "whose payment reference is exactly this reference. Bank lines "
        "without QR reference are matched as usual.",
    )
    exact_amount_only = fields.Boolean(
        help="Only match when the payment equals the open amount of the "
        "items found (one item, or several items taken in order). Otherwise "
        "the next rule is tried.",
    )

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

    def _is_applicable_for(self, st_line, partner):
        if not super()._is_applicable_for(st_line, partner):
            return False
        if not self.qr_type_ids:
            return True
        # T3622 Decode the QR reference: its type, its partner, its product
        return (
            st_line._get_qr_type() in self.qr_type_ids
            and bool(st_line._get_qr_partner())
            and bool(st_line._get_qr_reconcile_model())
        )

    def _get_exact_reference_candidates(self, st_line, partner, reference):
        """T3622 Open items whose payment reference is exactly the QR
        reference, also of the company and the other contacts of the partner
        (the reference is unique), oldest first."""
        domain = self.with_context(
            match_commercial_partner=True
        )._get_invoice_matching_amls_domain(st_line, partner)
        domain.append(("move_id.payment_reference", "=", reference))
        direction = "desc" if self.matching_order == "new_first" else "asc"
        amls = self.env["account.move.line"].search(
            domain,
            order=f"date_maturity {direction}, date {direction}, id {direction}",
        )
        if amls:
            return {"amls": amls, "allow_auto_reconcile": True}
        return None

    def _check_rule_propositions(self, st_line, amls_values_list):
        status = super()._check_rule_propositions(st_line, amls_values_list)
        if not self.exact_amount_only or "rejected" in status:
            return status
        # T3622 Only when the payment pays exactly the items found
        currency = st_line.foreign_currency_id or st_line.currency_id
        st_line_amount = st_line._prepare_move_line_default_vals()[1]["amount_currency"]
        amls_amount = sum(
            st_line._prepare_counterpart_amounts_using_st_line_rate(
                aml_values["aml"].currency_id,
                aml_values["amount_residual"],
                aml_values["amount_residual_currency"],
            )["amount_currency"]
            for aml_values in amls_values_list
        )
        if not currency.is_zero(st_line_amount + amls_amount):
            return {"rejected"}
        return status

    def _get_invoice_matching_amls_candidates(self, st_line, partner):
        reference = self.match_exact_reference and st_line._get_qr_reference()
        if reference:
            return self._get_exact_reference_candidates(st_line, partner, reference)
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
