import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    manual_product_id = fields.Many2one(
        comodel_name="product.product",
        check_company=True,
        store=False,
        default=False,
        prefetch=False,
    )
    manual_contract_id = fields.Many2one(
        comodel_name="recurring.contract",
        check_company=True,
        store=False,
        default=False,
        prefetch=False,
    )

    @api.onchange("manual_product_id")
    def on_change_manual_product_id(self):
        if self.manual_product_id:
            self.manual_account_id = (
                self.manual_product_id.property_account_income_id.id
            )
            arguments = {
                "product_id": self.manual_product_id.id,
                "product_categ_id": self.manual_product_id.categ_id.id,
                "partner_id": self.partner_id.id,
                "partner_category_id": self.partner_id.category_id.ids,
                "account_prefix": self.manual_account_id.code,
                "company_id": self.company_id.id,
            }
            self.analytic_distribution = self.env[
                "account.analytic.distribution.model"
            ]._get_distribution(arguments)

    @api.onchange("manual_contract_id")
    def on_change_manual_contract_id(self):
        # Make sure the reconcile data is updated when the contract changes
        self._onchange_manual_reconcile_vals()

    def _process_manual_reconcile_from_line(self, line):
        """Also restore manual_product_id and manual_contract_id from line data.

        The base implementation sets manual_account_id, manual_amount, etc. but
        not the custom fields added by this module. Without this override,
        _check_line_changed always detects a product/contract mismatch and
        _onchange_manual_reconcile_vals clears the product from the line dict.
        """
        res = super()._process_manual_reconcile_from_line(line)
        product_id = line.get("product_id")
        if isinstance(product_id, list | tuple):
            product_id = product_id[0]
        contract_id = line.get("contract_id")
        if isinstance(contract_id, list | tuple):
            contract_id = contract_id[0]
        self.manual_product_id = product_id or False
        self.manual_contract_id = contract_id or False
        return res

    def _get_manual_reconcile_vals(self):
        vals = super()._get_manual_reconcile_vals()
        vals["product_id"] = (
            self.manual_product_id.id,
            self.manual_product_id.display_name,
        )
        vals["contract_id"] = (
            self.manual_contract_id.id,
            self.manual_contract_id.display_name,
        )
        return vals

    def _reconcile_move_line_vals(self, line, move_id=False):
        vals = super()._reconcile_move_line_vals(line, move_id=move_id)
        product_id = line.get("product_id")
        if isinstance(product_id, list | tuple):
            product_id = product_id[0]
        contract_id = line.get("contract_id")
        if isinstance(contract_id, list | tuple):
            contract_id = contract_id[0]
        vals["product_id"] = product_id or False
        vals["contract_id"] = contract_id or False
        return vals

    def _reconcile_data_by_model(self, data, reconcile_model, reconcile_auxiliary_id):
        new_data, reconcile_auxiliary_id = super()._reconcile_data_by_model(
            data, reconcile_model, reconcile_auxiliary_id
        )
        contract = self._get_contract_from_reference()
        if contract:
            nb_kept_lines = len([line for line in data if line["kind"] != "suspense"])
            for line in new_data[nb_kept_lines:]:
                if not line.get("contract_id"):
                    line["contract_id"] = [contract.id, contract.display_name]
        return new_data, reconcile_auxiliary_id

    def _default_reconcile_data(self, from_unreconcile=False):
        res = super()._default_reconcile_data(from_unreconcile=from_unreconcile)
        if from_unreconcile or any(
            line["kind"] not in ("liquidity", "suspense") for line in res["data"]
        ):
            return res
        # No rule matched: prefill the gift button matching the QRR gift type
        reconcile_model = self._get_gift_reconcile_model()
        if not reconcile_model:
            return res
        data = [line for line in res["data"] if line["kind"] == "liquidity"]
        return self._recompute_suspense_line(
            *self._reconcile_data_by_model(
                data, reconcile_model, res["reconcile_auxiliary_id"]
            ),
            self.manual_reference,
        )

    def _get_gift_reconcile_model(self):
        model_obj = self.env["account.reconcile.model"]
        if not self._get_contract_from_reference():
            return model_obj
        gift_type = self.env["sponsorship.gift.type"].browse(
            int(self._get_gift_reference()[21])
        )
        if not gift_type.exists() or not gift_type.product_id:
            return model_obj
        return model_obj.search(
            [
                ("rule_type", "=", "writeoff_button"),
                ("company_id", "=", self.company_id.id),
                ("line_ids.product_id.product_tmpl_id", "=", gift_type.product_id.id),
            ],
            limit=1,
        )

    def _get_gift_reference(self):
        """Gift QRR reference, built as 9 digits + partner ref (7) + commitment
        number (5) + gift type (1-6) + 0000 + check digit. Type 0 (sponsorship)
        and fund donations (type 6 followed by the fund id) reuse the same
        layout, so they are skipped. The bank puts it in the label, or in the
        move ref when the donor wrote a message."""
        for ref in (self.ref, self.payment_ref):
            ref = (ref or "").strip()
            if re.fullmatch(r"\d{21}[1-6]0000\d", ref):
                return ref
        return ""

    def _get_contract_from_reference(self):
        contract_obj = self.env["recurring.contract"]
        ref = self._get_gift_reference()
        if not ref:
            return contract_obj
        partner_ref = ref[9:16].lstrip("0")
        contracts = contract_obj.search(
            [
                ("commitment_number", "=", int(ref[16:21])),
                ("state", "!=", "draft"),
                ("company_id", "=", self.company_id.id),
                "|",
                ("partner_id.ref", "=", partner_ref),
                ("correspondent_id.ref", "=", partner_ref),
            ]
        ).filtered(lambda c: c.gift_partner_id.ref == partner_ref)
        # Ended contracts don't block their commitment number from being reused
        current = contracts.filtered(
            lambda c: c.state not in ("terminated", "cancelled")
        )
        if len(current) == 1:
            return current
        return contracts if len(contracts) == 1 else contract_obj

    def _check_line_changed(self, line):
        res = super()._check_line_changed(line)
        product_id = line.get("product_id", (False,))
        if isinstance(product_id, int):
            product_id = (product_id,)
        contract_id = line.get("contract_id", (False,))
        if isinstance(contract_id, int):
            contract_id = (contract_id,)
        return (
            res
            or self.manual_product_id.id != product_id[0]
            or self.manual_contract_id.id != contract_id[0]
        )

    def _do_auto_reconcile(self, models):
        """Skip lines that fail to reconcile (e.g. sponsorship activation
        blocked by an unverified partner) instead of rolling back the
        whole statement import. The line stays open for manual reconcile."""
        try:
            with self.env.cr.savepoint():
                return super()._do_auto_reconcile(models)
        except UserError as error:
            _logger.warning(
                "Auto reconcile skipped for statement line %s: %s", self.id, error
            )
            self.move_id.message_post(
                body=self.env._(
                    "Automatic reconciliation skipped: %(error)s", error=error
                )
            )
            return False
