##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
"""Odoo 18 binding of the PayU GPO client.

Porting note (Odoo 19/20): the notification hooks of Odoo 18 are thin wrappers
around the _payu_gpo_* helpers below, which map one-to-one onto the new hooks:

    _payu_gpo_extract_reference   -> _extract_reference
    _payu_gpo_apply_order         -> _apply_updates
    _payu_gpo_extract_token_values -> _extract_token_values
    _send_payment_request          -> unchanged (called by _charge_with_token)

Keep business logic in the helpers (or in payu_client) so a port only rewires.
"""

import logging
from urllib.parse import parse_qsl, urlsplit

from werkzeug import urls

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.payment import utils as payment_utils

from .. import const
from ..controllers.main import PayuGpoController
from ..payu_client import PayuError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    # --- outgoing: hosted payment page (BLIK, bank transfers) ----------------

    def _get_specific_rendering_values(self, processing_values):
        """Order paid on the PayU hosted page.

        The hosted page cannot store a card for recurring charges (PayU only
        accepts recurring=FIRST with card data or a Secure Form token): cards
        go through the direct flow below.
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != const.PROVIDER_CODE:
            return res

        client = self.provider_id._payu_gpo_client()
        payload = client.build_order_payload(
            **self._payu_gpo_order_values(with_continue_url=True),
        )
        try:
            order = client.create_order(payload)
        except PayuError as e:
            raise ValidationError(_("PayU: %s", e)) from e
        self.provider_reference = order.get("orderId")
        redirect_uri = order.get("redirectUri")
        if not redirect_uri:
            raise ValidationError(_("PayU did not return a payment page."))
        parsed = urlsplit(redirect_uri)
        return {
            "api_url": redirect_uri,
            # GET forms drop the query string of their action: re-post it as inputs
            "url_params": dict(parse_qsl(parsed.query)),
        }

    # --- outgoing: cards, Secure Form token (direct flow) --------------------

    def _get_specific_processing_values(self, processing_values):
        res = super()._get_specific_processing_values(processing_values)
        if (
            self.provider_code != const.PROVIDER_CODE
            or self.operation != "online_direct"
        ):
            return res
        return {
            "payu_gpo_access_token": payment_utils.generate_access_token(
                self.reference
            ),
        }

    def _payu_gpo_pay_with_card_token(self, card_token, browser=None):
        """Charge the TOK_ token the Secure Form returned.

        :param dict browser: threeDsAuthentication.browser data; without it
                             PayU can only attempt 3DS, which issuers refuse
                             for a first recurring payment
        :return: the URL where the buyer must authenticate (3DS / CVV), or
                 None when PayU accepted the card right away
        """
        client = self.provider_id._payu_gpo_client()
        three_ds = {"browser": browser} if browser else {}
        if self.tokenize:
            # Strong authentication when storing the card for monthly charges.
            three_ds.update(challengeRequested="YES", recurring={"frequency": "30"})
        payload = client.build_order_payload(
            recurring="FIRST" if self.tokenize else None,
            pay_method={"type": "CARD_TOKEN", "value": card_token},
            three_ds=three_ds,
            **self._payu_gpo_order_values(with_continue_url=True),
        )
        try:
            response = client.create_order(payload)
        except PayuError as e:
            self._set_error(_("PayU: %s", e))
            return None
        self.provider_reference = response.get("orderId")
        if response.get("status", {}).get("statusCode", "").startswith("WARNING"):
            # The buyer comes back through the return route after 3DS.
            self._set_pending()
            return response.get("redirectUri")
        # Only an immediately accepted payment returns the multi-use token.
        pay_method = response.get("payMethods", {}).get("payMethod", {})
        if self.tokenize and pay_method.get("value", "").startswith("TOKC_"):
            self._payu_gpo_tokenize(
                {
                    "provider_ref": pay_method["value"],
                    "payment_details": pay_method.get("card", {}).get("number", "")[
                        -4:
                    ],
                }
            )
        self._payu_gpo_refresh_from_api()
        return None

    def _payu_gpo_refresh_from_api(self):
        """Read the order status from PayU (no webhook needed, e.g. on dev)."""
        order = self.provider_id._payu_gpo_client().get_order(self.provider_reference)
        for payu_order in order.get("orders", []):
            self._handle_notification_data(const.PROVIDER_CODE, {"order": payu_order})

    def _payu_gpo_order_values(self, with_continue_url=False):
        base_url = self.provider_id.get_base_url()
        first_name, last_name = payment_utils.split_partner_name(
            self.partner_name or ""
        )
        values = {
            "ext_order_id": self.reference,
            "description": self.reference,
            "amount_minor": str(
                payment_utils.to_minor_currency_units(self.amount, self.currency_id)
            ),
            "currency": self.currency_id.name,
            "customer_ip": payment_utils.get_customer_ip_address() or None,
            "notify_url": urls.url_join(
                self._payu_gpo_notify_base_url() or base_url,
                PayuGpoController._webhook_url,
            ),
            "buyer": {
                "extCustomerId": self._payu_gpo_ext_customer_id(),
                "email": self.partner_email,
                "firstName": first_name,
                "lastName": last_name,
                "phone": self.partner_phone,
                "language": (self.partner_lang or "pl")[:2],
            },
        }
        if with_continue_url:
            values["continue_url"] = urls.url_join(
                base_url, PayuGpoController._return_url
            )
        return values

    def _payu_gpo_notify_base_url(self):
        """Public URL PayU sends notifications to, when it differs from the
        base URL (reverse proxy, or a tunnel exposing only the webhook)."""
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("payment_payu_gpo.notify_base_url")
        )

    def _payu_gpo_ext_customer_id(self):
        """Stable buyer identifier PayU attaches the stored card tokens to."""
        return f"odoo-{self.env.cr.dbname}-{self.partner_id.commercial_partner_id.id}"

    # --- outgoing: merchant-initiated token charge --------------------------

    def _send_payment_request(self):
        """Charge the saved PayU card token, no buyer involvement.

        Called by my_compassion's off-session cron with operation="offline".
        The outcome arrives asynchronously through the webhook.
        """
        super()._send_payment_request()
        if self.provider_code != const.PROVIDER_CODE:
            return
        if not self.token_id:
            raise UserError(_("PayU: the transaction is not linked to a token."))

        client = self.provider_id._payu_gpo_client()
        payload = client.build_order_payload(
            recurring="STANDARD",
            pay_method={"type": "CARD_TOKEN", "value": self.token_id.provider_ref},
            **self._payu_gpo_order_values(),
        )
        try:
            order = client.create_order(payload)
        except PayuError as e:
            if self.operation == "offline":
                self._set_error(_("PayU: %s", e))
                return
            raise UserError(_("PayU: %s", e)) from e
        self.provider_reference = order.get("orderId")
        self._set_pending()

    def _send_refund_request(self, amount_to_refund=None):
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if self.provider_code != const.PROVIDER_CODE:
            return refund_tx
        client = self.provider_id._payu_gpo_client()
        try:
            client.refund(
                self.provider_reference,
                str(
                    payment_utils.to_minor_currency_units(
                        -refund_tx.amount, refund_tx.currency_id
                    )
                ),
                description=refund_tx.reference,
                ext_refund_id=refund_tx.reference,
            )
        except PayuError as e:
            refund_tx._set_error(_("PayU: %s", e))
            return refund_tx
        # The refund notification (refund.status FINALIZED) settles it.
        refund_tx._set_pending()
        return refund_tx

    # --- incoming: Odoo 18 hooks (thin wrappers) ----------------------------

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != const.PROVIDER_CODE or len(tx) == 1:
            return tx
        reference = self._payu_gpo_extract_reference(notification_data)
        tx = self.search(
            [("reference", "=", reference), ("provider_code", "=", provider_code)]
        )
        if not tx:
            raise ValidationError(
                _("PayU: no transaction found for reference %s.", reference)
            )
        return tx

    def _process_notification_data(self, notification_data):
        super()._process_notification_data(notification_data)
        if self.provider_code != const.PROVIDER_CODE:
            return
        self._payu_gpo_apply_order(notification_data)

    # --- incoming: version-independent helpers ------------------------------

    @api.model
    def _payu_gpo_extract_reference(self, notification_data):
        """Odoo reference of the transaction concerned by the notification.

        Refund notifications carry the refund's extRefundId (= refund tx reference).
        """
        refund = notification_data.get("refund")
        if refund and refund.get("extRefundId"):
            return refund["extRefundId"]
        reference = (notification_data.get("order") or {}).get("extOrderId")
        if not reference:
            raise ValidationError(_("PayU: received data with missing reference."))
        return reference

    def _payu_gpo_apply_order(self, notification_data):
        """Update state, provider reference and token from PayU data."""
        refund = notification_data.get("refund")
        if refund:
            status = refund.get("status")
            if status == "FINALIZED":
                self._set_done()
            elif status == "CANCELED":
                self._set_canceled(_("PayU canceled the refund."))
            return

        order = notification_data.get("order") or {}
        if order.get("orderId"):
            self.provider_reference = order["orderId"]
        status = order.get("status")
        if status in const.STATUS_MAPPING["pending"]:
            self._set_pending()
        elif status in const.STATUS_MAPPING["done"]:
            self._set_done()
            if self.tokenize and not self.token_id:
                self._payu_gpo_tokenize()
        elif status in const.STATUS_MAPPING["canceled"]:
            self._set_canceled()
        else:
            _logger.warning("PayU: unexpected status %s for %s", status, self.reference)
            self._set_error(_("PayU: received data with invalid status: %s", status))

    def _payu_gpo_tokenize(self, token_values=None):
        token_values = token_values or self._payu_gpo_extract_token_values()
        if not token_values:
            _logger.warning(
                "PayU: no card token found after payment %s", self.reference
            )
            return
        token = self.env["payment.token"].create(
            {
                "provider_id": self.provider_id.id,
                "payment_method_id": self.payment_method_id.id,
                "partner_id": self.partner_id.id,
                **token_values,
            }
        )
        self.write({"token_id": token.id, "tokenize": False})

    def _payu_gpo_extract_token_values(self):
        """Fetch the TOKC_ card token PayU stored for this buyer.

        Used after 3DS, when the order response did not carry the token.
        TODO(sandbox): validate that the trusted_merchant grant lists the card
        stored by a recurring=FIRST payment, and pick the right one when the
        buyer has several cards.
        """
        client = self.provider_id._payu_gpo_client()
        try:
            buyer_token = client.get_trusted_merchant_token(
                self.partner_email, self._payu_gpo_ext_customer_id()
            )
            methods = client.get_pay_methods(buyer_token)
        except PayuError as e:
            _logger.warning(
                "PayU: could not list card tokens for %s: %s", self.reference, e
            )
            return {}
        cards = [
            card
            for card in methods.get("cardTokens", [])
            if card.get("status") == "ACTIVE"
            and card.get("value", "").startswith("TOKC_")
        ]
        if not cards:
            return {}
        card = next((c for c in cards if c.get("preferred")), cards[0])
        return {
            "provider_ref": card["value"],
            "payment_details": card.get("cardNumberMasked", "")[-4:],
        }
