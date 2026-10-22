import hashlib
import ssl
from unittest.mock import MagicMock

import requests
import urllib3
from urllib3.exceptions import MaxRetryError, NewConnectionError

from odoo.tests import BaseCase, tagged

from .. import payu_client
from ..payu_client import (
    SANDBOX_HOST,
    PayuClient,
    PayuError,
    PayuUnknownOutcome,
    parse_signature_header,
    verify_signature,
)


def _response(status_code, payload):
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    return response


@tagged("post_install", "-at_install")
class TestPayuClient(BaseCase):
    """Plain-Python tests: no database, valid unchanged across Odoo versions."""

    def setUp(self):
        super().setUp()
        payu_client._TOKEN_CACHE.clear()
        self.addCleanup(payu_client._TOKEN_CACHE.clear)

    def _client(self, request=None, auth=None):
        session = MagicMock()
        session.post.return_value = auth or _response(
            200, {"access_token": "T", "expires_in": 43199}
        )
        if isinstance(request, Exception):
            session.request.side_effect = request
        else:
            session.request.return_value = request
        return PayuClient("1", "1", "s", sandbox=True, session=session), session

    def test_signature_header_parsing(self):
        parts = parse_signature_header(
            "sender=checkout;signature=abc;algorithm=MD5;content=DOCUMENT"
        )
        self.assertEqual(parts["signature"], "abc")
        self.assertEqual(parts["algorithm"], "MD5")

    def test_verify_signature(self):
        body = b'{"order":{"orderId":"X"}}'
        good = hashlib.md5(body + b"key").hexdigest()
        header = f"sender=checkout;signature={good};algorithm=MD5;content=DOCUMENT"
        self.assertTrue(verify_signature(body, header, "key"))
        self.assertFalse(verify_signature(body + b" ", header, "key"))
        self.assertFalse(verify_signature(body, header, "other"))
        self.assertFalse(verify_signature(body, None, "key"))
        sha = hashlib.sha256(body + b"key").hexdigest()
        self.assertTrue(
            verify_signature(body, f"signature={sha};algorithm=SHA-256", "key")
        )

    def test_order_payload(self):
        client = PayuClient("145227", "145227", "secret", sandbox=True)
        payload = client.build_order_payload(
            ext_order_id="S0001",
            description="S0001",
            amount_minor="5000",
            currency="PLN",
            customer_ip="10.0.0.1",
            notify_url="https://odoo/notify",
            recurring="STANDARD",
            pay_method={"type": "CARD_TOKEN", "value": "TOKC_X"},
            buyer={"email": "a@b.pl", "phone": False},
        )
        self.assertEqual(payload["merchantPosId"], "145227")
        self.assertEqual(payload["recurring"], "STANDARD")
        self.assertEqual(payload["payMethods"]["payMethod"]["value"], "TOKC_X")
        self.assertEqual(payload["buyer"], {"email": "a@b.pl"})
        self.assertNotIn("continueUrl", payload)

    def test_token_cached_and_order_created(self):
        session = MagicMock()
        session.post.return_value = _response(
            200, {"access_token": "T", "expires_in": 43199}
        )
        session.request.return_value = _response(
            302,
            {
                "status": {"statusCode": "SUCCESS"},
                "redirectUri": "https://pay/x",
                "orderId": "O1",
            },
        )
        # One client per API call, as the provider creates them.
        PayuClient("1", "1", "s", sandbox=True, session=session).create_order({})
        PayuClient("1", "1", "s", sandbox=True, session=session).create_order({})
        self.assertEqual(session.post.call_count, 1, "OAuth token must be cached")
        method, url = session.request.call_args.args
        self.assertEqual((method, url), ("POST", SANDBOX_HOST + "/api/v2_1/orders"))
        self.assertFalse(session.request.call_args.kwargs["allow_redirects"])

    def test_error_raised(self):
        session = MagicMock()
        session.post.return_value = _response(
            200, {"access_token": "T", "expires_in": 100}
        )
        session.request.return_value = _response(
            400, {"status": {"statusCode": "ERROR_VALUE_INVALID", "statusDesc": "Bad"}}
        )
        client = PayuClient("1", "1", "s", session=session)
        with self.assertRaises(PayuError) as ctx:
            client.get_order("O1")
        self.assertEqual(ctx.exception.payu_status, "ERROR_VALUE_INVALID")

    def test_expired_token_asked_again_after_401(self):
        client, session = self._client(
            _response(401, {"status": {"statusCode": "UNAUTHORIZED"}})
        )
        with self.assertRaises(PayuError):
            client.get_order("O1")
        session.request.return_value = _response(200, {"orders": []})
        client.get_order("O1")
        self.assertEqual(session.post.call_count, 2)

    def test_unknown_outcome(self):
        """No answer is not a refusal: the order may exist at PayU."""
        for failure in (
            requests.exceptions.ReadTimeout("slow"),
            requests.exceptions.ConnectionError("reset"),
            _response(503, {}),
        ):
            client, _session = self._client(failure)
            with self.assertRaises(PayuUnknownOutcome) as ctx:
                client.create_order({})
            self.assertFalse(ctx.exception.definitive)

    def test_definitive_errors(self):
        """PayU refused, or the request never left: nothing happened there."""
        for failure in (
            requests.exceptions.ConnectTimeout("unreachable"),
            _response(400, {"status": {"statusCode": "ERROR_VALUE_INVALID"}}),
        ):
            client, _session = self._client(failure)
            with self.assertRaises(PayuError) as ctx:
                client.create_order({})
            self.assertTrue(ctx.exception.definitive)

    def test_connection_never_made_is_definitive(self):
        """Refused or unresolved (urllib3 NewConnectionError): nothing sent."""
        failure = requests.exceptions.ConnectionError(
            MaxRetryError(None, "/api", reason=NewConnectionError(None, "refused"))
        )
        client, _session = self._client(failure)
        with self.assertRaises(PayuError) as ctx:
            client.create_order({})
        self.assertTrue(ctx.exception.definitive)

    def test_ssl_error_may_come_after_the_request(self):
        """A TLS error may happen while reading PayU's answer, the order
        sent: only a certificate check is sure to come before (requests
        wraps both the same way)."""
        for ssl_error, definitive in (
            (ssl.SSLError(1, "[SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC]"), False),
            (ssl.SSLCertVerificationError(1, "certificate verify failed"), True),
        ):
            failure = requests.exceptions.SSLError(
                MaxRetryError(
                    None, "/api", reason=urllib3.exceptions.SSLError(ssl_error)
                )
            )
            client, _session = self._client(failure)
            with self.assertRaises(PayuError) as ctx:
                client.create_order({})
            self.assertEqual(ctx.exception.definitive, definitive, ssl_error)

    def test_invalid_authentication_answers_are_payu_errors(self):
        """Only PayuError leaves the client, whatever PayU sends back."""
        html = _response(200, None)
        html.json.side_effect = ValueError("not JSON")
        for auth in (html, _response(200, {"expires_in": 100})):
            client, session = self._client(_response(200, {}), auth=auth)
            with self.assertRaises(PayuError) as ctx:
                client.get_order("O1")
            self.assertTrue(ctx.exception.definitive)
            session.request.assert_not_called()
