import re

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountReconcileModel(models.Model):
    _inherit = "account.reconcile.model"

    partner_matching_ids = fields.One2many(
        "account.reconcile.model.partner.matching", "model_id", "Partner Matching Rules"
    )
    only_this_month = fields.Boolean(
        default=False, help="Check to search only from the start of the month"
    )

    @api.onchange("past_months_limit")
    def _uncheck_only_this_month(self):
        if self.past_months_limit and self.only_this_month:
            self.only_this_month = False

    def _get_partner_from_mapping(self, st_line):
        partner = super()._get_partner_from_mapping(st_line)
        if not partner:
            for matching in self.partner_matching_ids:
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
            date_limit = st_line_date.replace(day=1)
            domain.append(
                ("date", ">=", fields.Date.to_string(date_limit)),
            )
        return domain


class AccountReconcileModelPartnerMatching(models.Model):
    _name = "account.reconcile.model.partner.matching"
    _description = "Partner matching rule for reconciliation models"
    _order = "sequence"

    model_id = fields.Many2one(
        "account.reconcile.model", "Reconcile Model", required=True, ondelete="cascade"
    )
    sequence = fields.Integer("Sequence", default=10, required=True)
    statement_field_id = fields.Many2one(
        "ir.model.fields",
        "Statement Field",
        domain=[
            ("model", "in", ["account.bank.statement.line", "account.move"]),
            ("store", "=", True),
            ("ttype", "in", ["char", "text", "html"]),
        ],
        required=True,
        ondelete="cascade",
    )
    extract_regex = fields.Char(
        "Extract Regex",
        help="Regular expression to extract the value from the statement field",
    )
    lookup_field_id = fields.Many2one(
        "ir.model.fields",
        "Lookup Field",
        domain=[
            "|",
            ("model", "=", "res.partner"),
            ("model_id.field_id.relation", "=", "res.partner"),
        ],
        required=True,
        ondelete="cascade",
    )
    lookup_model = fields.Char(related="lookup_field_id.model_id.model")
    partner_field_id = fields.Many2one(
        "ir.model.fields",
        "Partner Field",
    )
    search_operator = fields.Selection(
        [
            ("=", "="),
            ("ilike", "contains"),
        ],
        "Search Operator",
        default="ilike",
        required=True,
    )
    unique_match = fields.Boolean(
        "Unique Match",
        help="If unchecked, the first matching partner will be assigned",
        default=True,
    )
    partner_model_id = fields.Integer(compute="_compute_partner_model_id")

    def _compute_partner_model_id(self):
        partner_model = self.env["ir.model"].search([("model", "=", "res.partner")])
        for record in self:
            record.partner_model_id = partner_model.id

    @api.constrains("extract_regex")
    def _check_extract_regex(self):
        for record in self:
            if record.extract_regex:
                try:
                    re.compile(record.extract_regex)
                except re.error as e:
                    raise ValidationError(_("Invalid regex: %s") % e) from e

    @api.onchange("lookup_field_id")
    def _onchange_lookup_field_id(self):
        self.partner_field_id = False

    def match_line(self, bank_statement_line):
        self.ensure_one()
        statement_value = bank_statement_line[self.statement_field_id.name]
        partner_obj = self.env["res.partner"]
        if statement_value:
            if self.extract_regex:
                re.match()
                match = re.search(self.extract_regex, statement_value)
                if match:
                    statement_value = match.group(0)
                else:
                    return partner_obj
            found_record = self.env[self.lookup_model].search(
                [
                    (self.lookup_field_id.name, self.search_operator, statement_value),
                ],
                limit=10,
            )
            if self.partner_field_id:
                partner = found_record.mapped(self.partner_field_id.name)
            else:
                partner = found_record
            if len(partner) == 1 or not self.unique_match:
                return partner[:1]
        return partner_obj
