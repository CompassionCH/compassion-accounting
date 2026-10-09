import hashlib
import json

from odoo.tests import tagged
from odoo.tests.common import JsonRpcException
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon

from ..controllers.main import PayuGpoController
from .common import SECOND_KEY, PayuGpoCommon


@tagged("post_install", "-at_install")
class TestWebhook(PayuGpoCommon, PaymentHttpCommon):
    def _post(self, payload, signature=None):
        body = json.dumps(payload).encode()
        signature = signature or hashlib.md5(body + SECOND_KEY.encode()).hexdigest()
        return self.url_open(
            self._build_url(PayuGpoController._webhook_url),
            data=body,
            headers={
                "Content-Type": "application/json",
                "OpenPayu-Signature": (
                    f"sender=checkout;signature={signature};algorithm=MD5;"
                    "content=DOCUMENT"
                ),
            },
        )

    @mute_logger("odoo.addons.payment_payu_gpo.controllers.main")
    def test_signed_notification_updates_transaction(self):
        tx = self._create_transaction(flow="redirect")
        response = self._post(self._order_notification("COMPLETED"))
        self.assertEqual(response.status_code, 200)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "done")

    @mute_logger("odoo.addons.payment_payu_gpo.controllers.main", "odoo.http")
    def test_bad_signature_is_rejected(self):
        tx = self._create_transaction(flow="redirect")
        response = self._post(self._order_notification("COMPLETED"), signature="0" * 32)
        self.assertEqual(response.status_code, 403)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "draft")

    @mute_logger("odoo.http")
    def test_card_payment_rejects_tampered_access_token(self):
        tx = self._create_transaction(flow="direct")
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request(
                self._build_url(PayuGpoController._card_payment_url),
                {"reference": tx.reference, "access_token": "x", "card_token": "TOK_X"},
            )
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "draft")
