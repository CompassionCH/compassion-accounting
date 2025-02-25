import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    predefined_extract = fields.Selection(
        "list_match_functions",
        "Extract Value",
        help="Provide a function used to extract the value from the statement field."
        "Use 'custom' for giving a custom regex",
    )
    extract_regex = fields.Char(
        "Custom Regex",
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
    is_active = fields.Boolean("Active", default=True)

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
            if self.predefined_extract:
                statement_value = getattr(self, self.predefined_extract)(
                    statement_value
                )
                if not statement_value:
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

    def list_match_functions(self):
        """
        Utility method to list all functions starting with 'match_'
        along with their docstrings.
        """
        match_methods = []
        for attr_name in dir(self):
            if attr_name.startswith("_match_"):
                method = getattr(self, attr_name)
                if callable(method):
                    docstring = method.__doc__ or "No docstring available"
                    match_methods.append((attr_name, docstring))
        return match_methods

    def _match_child_ref(self, statement_value):
        """
        Match a child LocalID
        """
        child_regex = r"\b[a-zA-Z]{2}(\d{3,4})(\d{4,5})\b"
        match = re.search(child_regex, statement_value)
        if match:
            ref = match.group(0)
            if len(ref) == 9:
                ref = f"0{match.group(1)}0{match.group(2)}"
        else:
            ref = False
        return ref

    def _match_custom(self, statement_value):
        """
        Custom regex
        """
        match = re.search(self.extract_regex, statement_value)
        return match.group(0) if match else False
