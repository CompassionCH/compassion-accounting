import hashlib
from unittest.mock import MagicMock

from odoo.tests import BaseCase, tagged

from ..payu_client import (
    SANDBOX_HOST,
    PayuClient,
    PayuError,
    parse_signature_header,
    to_minor_units,
    verify_signature,
)


def _response(status_code, payload):
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    return response


@tagged("post_install", "-at_install")
class TestPayuClient(BaseCase):
    """Plain-Python tests: no database, valid unchanged across Odoo versions."""

    def test_minor_units(self):
        self.assertEqual(to_minor_units(12.5), "1250")
        self.assertEqual(to_minor_units(0.1 + 0.2), "30")

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
        client = PayuClient("1", "1", "s", sandbox=True, session=session)
        client.create_order({})
        client.create_order({})
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
