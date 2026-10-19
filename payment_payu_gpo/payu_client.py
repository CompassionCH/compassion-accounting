##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
"""Plain-Python client for the PayU GPO (Europe) REST API v2.1.

This module must stay free of any Odoo import: it holds everything that will
not change when the Odoo payment framework does (Odoo 19/20 rewrote the
notification hooks). The Odoo layer only maps its results onto transactions.

API reference: https://developers.payu.com/europe/api/
"""

import hashlib
import hmac
import logging
import time

import requests

_logger = logging.getLogger(__name__)

PRODUCTION_HOST = "https://secure.payu.com"
SANDBOX_HOST = "https://secure.snd.payu.com"
TIMEOUT = 20

# Algorithms PayU may announce in the OpenPayu-Signature header.
SIGNATURE_ALGORITHMS = {
    "MD5": hashlib.md5,
    "SHA": hashlib.sha1,
    "SHA1": hashlib.sha1,
    "SHA-256": hashlib.sha256,
    "SHA256": hashlib.sha256,
    "SHA-384": hashlib.sha384,
    "SHA-512": hashlib.sha512,
}


class PayuError(Exception):
    """Anything that goes wrong talking to PayU: the client raises nothing else.

    definitive: PayU answered and refused the request, so nothing happened on
    its side. Otherwise the outcome is unknown (see PayuUnknownOutcome).
    """

    definitive = True

    def __init__(self, message, status_code=None, payu_status=None):
        super().__init__(message)
        self.status_code = status_code
        self.payu_status = payu_status


class PayuUnknownOutcome(PayuError):
    """PayU did not answer (timeout, connection lost) or failed (5xx): the
    request may have been carried out all the same, e.g. an order created."""

    definitive = False


def parse_signature_header(header):
    """Split 'sender=checkout;signature=abc;algorithm=MD5;content=DOCUMENT'."""
    parts = {}
    for chunk in (header or "").split(";"):
        key, sep, value = chunk.partition("=")
        if sep:
            parts[key.strip()] = value.strip()
    return parts


def verify_signature(raw_body, header, second_key):
    """Check the OpenPayu-Signature header of a notification.

    PayU signs the exact request body concatenated with the POS "second key".

    :param bytes raw_body: the body exactly as received
    :param str header: value of the OpenPayu-Signature header
    :param str second_key: the POS second key (MD5 key)
    :return: True if the signature matches
    """
    parts = parse_signature_header(header)
    expected = parts.get("signature")
    algorithm = SIGNATURE_ALGORITHMS.get(parts.get("algorithm", "MD5").upper())
    if not expected or not algorithm or not second_key:
        return False
    if isinstance(raw_body, str):
        raw_body = raw_body.encode()
    computed = algorithm(raw_body + second_key.encode()).hexdigest()
    return hmac.compare_digest(computed, expected.lower())


# OAuth client_credentials tokens, per process: (host, client_id, secret) ->
# (token, expiry). A client is created for every API call.
_TOKEN_CACHE = {}


class PayuClient:
    """Stateless apart from the OAuth access tokens cached per process."""

    def __init__(self, pos_id, client_id, client_secret, sandbox=False, session=None):
        self.pos_id = str(pos_id)
        self.client_id = str(client_id)
        self.client_secret = client_secret
        self.host = SANDBOX_HOST if sandbox else PRODUCTION_HOST
        self.session = session or requests

    # --- authentication --------------------------------------------------

    def get_access_token(self):
        """OAuth client_credentials token, cached until shortly before expiry."""
        token, expiry = _TOKEN_CACHE.get(self._cache_key, (None, 0))
        if token and time.time() < expiry - 60:
            return token
        data = self._post_form(
            "/pl/standard/user/oauth/authorize",
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        token = self._access_token(data)
        _TOKEN_CACHE[self._cache_key] = (
            token,
            time.time() + int(data.get("expires_in") or 0),
        )
        return token

    @property
    def _cache_key(self):
        return (self.host, self.client_id, self.client_secret)

    def get_trusted_merchant_token(self, email, ext_customer_id):
        """OAuth token scoped to one buyer, required to list their card tokens.

        TODO(sandbox): confirm the grant is enabled on the POS together with
        recurring payments.
        """
        data = self._post_form(
            "/pl/standard/user/oauth/authorize",
            {
                "grant_type": "trusted_merchant",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "email": email,
                "ext_customer_id": ext_customer_id,
            },
        )
        return self._access_token(data)

    @staticmethod
    def _access_token(data):
        if not isinstance(data, dict) or not data.get("access_token"):
            raise PayuError("PayU sent no access token")
        return data["access_token"]

    # --- orders ------------------------------------------------------------

    def create_order(self, payload):
        """POST /api/v2_1/orders.

        PayU answers 302 (redirect flow) or 201 (token charge) with a JSON body
        holding orderId, redirectUri and status; redirects must not be followed.
        """
        return self._request(
            "POST", "/api/v2_1/orders", json=payload, ok=(200, 201, 302)
        )

    def get_order(self, order_id):
        return self._request("GET", f"/api/v2_1/orders/{order_id}")

    def refund(self, order_id, amount_minor, description, ext_refund_id):
        payload = {
            "refund": {
                "description": description,
                "amount": amount_minor,
                "extRefundId": ext_refund_id,
            }
        }
        return self._request(
            "POST", f"/api/v2_1/orders/{order_id}/refunds", json=payload
        )

    def get_pay_methods(self, buyer_token):
        """List the buyer's stored card tokens (cardTokens) and BLIK tokens."""
        return self._request("GET", "/api/v2_1/paymethods", token=buyer_token)

    # --- payload builders --------------------------------------------------

    def build_order_payload(
        self,
        *,
        ext_order_id,
        description,
        amount_minor,
        currency,
        customer_ip,
        notify_url,
        continue_url=None,
        buyer=None,
        recurring=None,
        card_on_file=None,
        pay_method=None,
        three_ds=None,
    ):
        """Assemble an order.

        recurring is None, "FIRST" or "STANDARD" (scheduled recurring
        charges); card_on_file is None, "FIRST", "STANDARD_CARDHOLDER" or
        "STANDARD_MERCHANT" (a card saved without a schedule). PayU refuses
        an order with both.

        pay_method is e.g. {"type": "CARD_TOKEN", "value": "TOKC_..."} for a
        merchant-initiated charge.
        """
        if recurring and card_on_file:
            raise ValueError("an order is either recurring or card on file")
        payload = {
            "notifyUrl": notify_url,
            "customerIp": customer_ip or "127.0.0.1",
            "merchantPosId": self.pos_id,
            "description": description,
            "currencyCode": currency,
            "totalAmount": amount_minor,
            "extOrderId": ext_order_id,
            "products": [
                {"name": description, "unitPrice": amount_minor, "quantity": "1"}
            ],
        }
        if continue_url:
            payload["continueUrl"] = continue_url
        if buyer:
            payload["buyer"] = {k: v for k, v in buyer.items() if v}
        if recurring:
            payload["recurring"] = recurring
        if card_on_file:
            payload["cardOnFile"] = card_on_file
        if pay_method:
            payload["payMethods"] = {"payMethod": pay_method}
        if three_ds:
            payload["threeDsAuthentication"] = three_ds
        return payload

    # --- transport ---------------------------------------------------------

    def _post_form(self, path, data):
        # Authentication only: whatever fails, the request it was for has not
        # been sent yet.
        try:
            response = self.session.post(self.host + path, data=data, timeout=TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise PayuError(f"Could not reach PayU: {e}") from e
        if response.status_code != 200:
            raise PayuError(
                f"PayU authentication failed ({response.status_code})",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as e:
            raise PayuError("PayU sent an invalid response") from e

    def _request(self, method, path, json=None, ok=(200, 201), token=None):
        headers = {"Authorization": f"Bearer {token or self.get_access_token()}"}
        try:
            response = self.session.request(
                method,
                self.host + path,
                json=json,
                headers=headers,
                timeout=TIMEOUT,
                allow_redirects=False,
            )
        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.SSLError,
        ) as e:
            # The request never reached PayU.
            raise PayuError(f"Could not reach PayU: {e}") from e
        except requests.exceptions.RequestException as e:
            # Timeout or connection lost while PayU may be processing it.
            raise PayuUnknownOutcome(f"PayU did not answer: {e}") from e
        if response.status_code == 401 and not token:
            # Revoked or expired before its announced expiry: ask a new one
            # next time.
            _TOKEN_CACHE.pop(self._cache_key, None)
        if response.status_code >= 500:
            raise PayuUnknownOutcome(
                f"PayU error {response.status_code}", status_code=response.status_code
            )
        try:
            data = response.json()
        except ValueError:
            data = {}
        status = data.get("status", {}) if isinstance(data, dict) else {}
        if response.status_code not in ok or status.get(
            "statusCode", "SUCCESS"
        ) not in (
            "SUCCESS",
            "WARNING_CONTINUE_REDIRECT",
            "WARNING_CONTINUE_3DS",
            "WARNING_CONTINUE_CVV",
        ):
            raise PayuError(
                status.get("statusDesc") or f"PayU error {response.status_code}",
                status_code=response.status_code,
                payu_status=status.get("statusCode"),
            )
        return data
