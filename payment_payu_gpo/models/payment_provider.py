##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import json

from odoo import api, fields, models

from .. import const
from ..payu_client import PRODUCTION_HOST, SANDBOX_HOST, PayuClient, PayuError


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[(const.PROVIDER_CODE, "PayU GPO")],
        ondelete={const.PROVIDER_CODE: "set default"},
    )
    payu_gpo_pos_id = fields.Char(
        "POS ID", required_if_provider=const.PROVIDER_CODE, groups="base.group_system"
    )
    payu_gpo_client_id = fields.Char(
        "OAuth client_id",
        required_if_provider=const.PROVIDER_CODE,
        groups="base.group_system",
    )
    payu_gpo_client_secret = fields.Char(
        "OAuth client_secret",
        required_if_provider=const.PROVIDER_CODE,
        groups="base.group_system",
    )
    payu_gpo_second_key = fields.Char(
        "Second key (MD5)",
        required_if_provider=const.PROVIDER_CODE,
        groups="base.group_system",
        help="Used to verify the OpenPayu-Signature of notifications.",
    )

    def _compute_feature_support_fields(self):  # pylint: disable=missing-return
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == const.PROVIDER_CODE).update(
            {
                "support_refund": "partial",
                "support_tokenization": True,
            }
        )

    def _get_supported_currencies(self):
        currencies = super()._get_supported_currencies()
        if self.code == const.PROVIDER_CODE:
            currencies = currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return currencies

    def _get_default_payment_method_codes(self):
        codes = super()._get_default_payment_method_codes()
        if self.code != const.PROVIDER_CODE:
            return codes
        return const.DEFAULT_PAYMENT_METHOD_CODES

    @api.model
    def _get_compatible_providers(self, *args, is_validation=False, **kwargs):
        """PayU stores a card only with a payment: a card validation (saving a
        card without paying) needs a zero-amount order, which PayU enables on
        a POS only on request, and is not implemented."""
        providers = super()._get_compatible_providers(
            *args, is_validation=is_validation, **kwargs
        )
        if is_validation:
            providers = providers.filtered(lambda p: p.code != const.PROVIDER_CODE)
        return providers

    def _payu_gpo_client(self):
        """The plain-Python API client configured for this provider.

        A disabled provider never calls PayU: on a neutralized copy of the
        production database, its keys are wiped, and the crons, status reads
        and refunds must not reach the production API anyway.
        """
        self.ensure_one()
        if self.state == "disabled":
            raise PayuError(f"the payment provider {self.name} is disabled")
        return PayuClient(
            pos_id=self.payu_gpo_pos_id,
            client_id=self.payu_gpo_client_id,
            client_secret=self.payu_gpo_client_secret,
            sandbox=self.state == "test",
        )

    def _payu_gpo_get_inline_form_values(self, payment_method_code):
        """Secure Form settings for the payment form, or "" for non-card methods."""
        self.ensure_one()
        if payment_method_code not in const.CARD_PAYMENT_METHOD_CODES:
            return ""
        sandbox = self.state == "test"
        return json.dumps(
            {
                "pos_id": self.payu_gpo_pos_id,
                "sdk_url": (SANDBOX_HOST if sandbox else PRODUCTION_HOST)
                + const.SDK_PATH,
                # The SDK refuses plain http outside its dev mode (localhost).
                "dev": sandbox,
                "lang": (self.env.lang or "en")[:2],
            }
        )
