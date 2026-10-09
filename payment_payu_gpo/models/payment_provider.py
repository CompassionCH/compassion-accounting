##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import json

from odoo import fields, models

from .. import const
from ..payu_client import PRODUCTION_HOST, SANDBOX_HOST, PayuClient


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

    def _payu_gpo_client(self):
        """The plain-Python API client configured for this provider."""
        self.ensure_one()
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
                "lang": (self.env.lang or "pl")[:2],
            }
        )
