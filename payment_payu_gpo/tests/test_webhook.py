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
    def _post(self, payload, signature=None, body=None, signed=True):
        body = body if body is not None else json.dumps(payload).encode()
        signature = signature or hashlib.md5(body + SECOND_KEY.encode()).hexdigest()
        headers = {"Content-Type": "application/json"}
        if signed:
            headers["OpenPayu-Signature"] = (
                f"sender=checkout;signature={signature};algorithm=MD5;content=DOCUMENT"
            )
        return self.url_open(
            self._build_url(PayuGpoController._webhook_url), data=body, headers=headers
        )

    def _pay_card(self, tx, card_token="TOK_X"):
        return self.make_jsonrpc_request(
            self._build_url(PayuGpoController._card_payment_url),
            {
                "reference": tx.reference,
                "access_token": self._generate_test_access_token(tx.reference),
                "card_token": card_token,
            },
        )

    def _cancel(self, tx, access_token=None):
        return self.make_jsonrpc_request(
            self._build_url(PayuGpoController._cancel_url),
            {
                "reference": tx.reference,
                "access_token": access_token
                or self._generate_test_access_token(tx.reference),
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

    @mute_logger("odoo.addons.payment_payu_gpo.controllers.main", "odoo.http")
    def test_unsigned_or_invalid_requests_are_refused(self):
        tx = self._create_transaction(flow="redirect")
        notification = self._order_notification("COMPLETED")
        self.assertEqual(self._post(notification, signed=False).status_code, 400)
        self.assertEqual(self._post(None, body=b"<html>").status_code, 400)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "draft")

    @mute_logger("odoo.addons.payment_payu_gpo.controllers.main", "odoo.http")
    def test_unknown_reference_is_sent_again(self):
        """Not acknowledged: the transaction may not be committed yet."""
        response = self._post(self._order_notification("COMPLETED", "not-yet"))
        self.assertEqual(response.status_code, 404)

    @mute_logger("odoo.addons.payment_payu_gpo.controllers.main")
    def test_notification_without_reference_is_acknowledged(self):
        self.assertEqual(self._post({"order": {"status": "NEW"}}).status_code, 200)

    @mute_logger("odoo.http")
    def test_card_payment_needs_a_secure_form_token(self):
        tx = self._create_transaction(flow="direct")
        with self.assertRaises(JsonRpcException):
            self._pay_card(tx, card_token="TOKC_SAVED")
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "draft")

    def test_card_payment_replayed_goes_to_the_status_page(self):
        """A replay of the request (Odoo retries it on a concurrent update)
        must not fail a payment PayU already has."""
        tx = self._create_transaction(
            flow="direct", state="pending", provider_reference=self.order_id
        )
        self.assertEqual(self._pay_card(tx), {"redirect_url": None})

    def test_refused_card_cancels_its_draft(self):
        """The Secure Form refused the card: nothing reached PayU, and the
        draft would block what it pays until it is cleaned up."""
        tx = self._create_transaction(flow="direct")
        self._cancel(tx)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "cancel")

    @mute_logger("odoo.http")
    def test_cancel_needs_the_access_token(self):
        tx = self._create_transaction(flow="direct")
        with self.assertRaises(JsonRpcException):
            self._cancel(tx, access_token="x")
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "draft")

    def test_cancel_leaves_a_payment_sent_to_payu(self):
        """Only a draft is cancelled: PayU has the others."""
        tx = self._create_transaction(
            flow="direct", state="pending", provider_reference=self.order_id
        )
        self._cancel(tx)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "pending")
