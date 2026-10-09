import json
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.payment import utils as payment_utils

from ..payu_client import PayuError
from .common import PayuGpoCommon

CLIENT = "odoo.addons.payment_payu_gpo.payu_client.PayuClient"


@tagged("post_install", "-at_install")
class TestPaymentTransaction(PayuGpoCommon):
    def test_redirect_creates_hosted_page_order(self):
        """The hosted page cannot store cards: no recurring flag there."""
        tx = self._create_transaction(flow="redirect", tokenize=True)
        with patch(
            f"{CLIENT}.create_order",
            return_value={
                "orderId": self.order_id,
                "redirectUri": "https://pay.example/?a=1",
            },
        ) as create_order:
            values = tx._get_specific_rendering_values(None)
        payload = create_order.call_args.args[0]
        self.assertNotIn("recurring", payload)
        self.assertNotIn("payMethods", payload)
        self.assertEqual(payload["totalAmount"], "111111")
        self.assertEqual(payload["currencyCode"], "PLN")
        self.assertEqual(payload["extOrderId"], tx.reference)
        self.assertEqual(values["url_params"], {"a": "1"})
        self.assertEqual(tx.provider_reference, self.order_id)

    def test_notify_base_url_parameter(self):
        """Only the notifications go to the public URL, the buyer returns
        to the base URL."""
        tx = self._create_transaction(flow="redirect")
        base_url = self.provider.get_base_url()
        values = tx._payu_gpo_order_values(with_continue_url=True)
        self.assertEqual(values["notify_url"], f"{base_url}/payment/payu_gpo/webhook")
        self.env["ir.config_parameter"].set_param(
            "payment_payu_gpo.notify_base_url", "https://hooks.example"
        )
        values = tx._payu_gpo_order_values(with_continue_url=True)
        self.assertEqual(
            values["notify_url"], "https://hooks.example/payment/payu_gpo/webhook"
        )
        self.assertEqual(values["continue_url"], f"{base_url}/payment/payu_gpo/return")

    def test_inline_form_values_only_for_cards(self):
        values = json.loads(self.provider._payu_gpo_get_inline_form_values("card"))
        self.assertEqual(values["pos_id"], "300746")
        self.assertTrue(values["sdk_url"].endswith("/javascript/sdk"))
        self.assertFalse(self.provider._payu_gpo_get_inline_form_values("blik"))

    def test_direct_flow_access_token(self):
        tx = self._create_transaction(flow="direct")
        with patch(
            "odoo.addons.payment.utils.generate_access_token",
            new=self._generate_test_access_token,
        ):
            values = tx._get_processing_values()
            self.assertTrue(
                payment_utils.check_access_token(
                    values["payu_gpo_access_token"], tx.reference
                )
            )

    def test_card_token_accepted_stores_multi_use_token(self):
        tx = self._create_transaction(flow="direct", tokenize=True)
        with (
            patch(
                f"{CLIENT}.create_order",
                return_value={
                    "orderId": self.order_id,
                    "status": {"statusCode": "SUCCESS"},
                    "payMethods": {
                        "payMethod": {
                            "type": "CARD_TOKEN",
                            "value": "TOKC_NEW",
                            "card": {"number": "444433******1111"},
                        }
                    },
                },
            ) as create_order,
            patch(
                f"{CLIENT}.get_order",
                return_value={
                    "orders": [self._order_notification("COMPLETED")["order"]]
                },
            ),
        ):
            redirect_url = tx._payu_gpo_pay_with_card_token(
                "TOK_ONCE", {"screenWidth": 1920}
            )
        payload = create_order.call_args.args[0]
        self.assertEqual(payload["recurring"], "FIRST")
        self.assertEqual(
            payload["threeDsAuthentication"],
            {
                "browser": {"screenWidth": 1920},
                "challengeRequested": "YES",
                "recurring": {"frequency": "30"},
            },
        )
        self.assertEqual(
            payload["payMethods"]["payMethod"],
            {"type": "CARD_TOKEN", "value": "TOK_ONCE"},
        )
        self.assertIn("continueUrl", payload)
        self.assertIsNone(redirect_url)
        self.assertEqual(tx.state, "done")
        self.assertEqual(tx.token_id.provider_ref, "TOKC_NEW")
        self.assertEqual(tx.token_id.payment_details, "1111")

    def test_card_token_without_tokenization(self):
        tx = self._create_transaction(flow="direct")
        with (
            patch(
                f"{CLIENT}.create_order",
                return_value={
                    "orderId": self.order_id,
                    "status": {"statusCode": "SUCCESS"},
                },
            ) as create_order,
            patch(
                f"{CLIENT}.get_order",
                return_value={
                    "orders": [self._order_notification("COMPLETED")["order"]]
                },
            ),
        ):
            tx._payu_gpo_pay_with_card_token("TOK_ONCE")
        self.assertNotIn("recurring", create_order.call_args.args[0])
        self.assertNotIn("threeDsAuthentication", create_order.call_args.args[0])
        self.assertEqual(tx.state, "done")
        self.assertFalse(tx.token_id)

    def test_card_token_3ds_redirects_buyer(self):
        tx = self._create_transaction(flow="direct", tokenize=True)
        with patch(
            f"{CLIENT}.create_order",
            return_value={
                "orderId": self.order_id,
                "status": {"statusCode": "WARNING_CONTINUE_3DS"},
                "redirectUri": "https://3ds.example/",
            },
        ):
            redirect_url = tx._payu_gpo_pay_with_card_token("TOK_ONCE")
        self.assertEqual(redirect_url, "https://3ds.example/")
        self.assertEqual(tx.state, "pending")
        self.assertFalse(tx.token_id)

    def test_card_token_refused(self):
        tx = self._create_transaction(flow="direct")
        with patch(f"{CLIENT}.create_order", side_effect=PayuError("declined")):
            self.assertIsNone(tx._payu_gpo_pay_with_card_token("TOK_ONCE"))
        self.assertEqual(tx.state, "error")

    def test_order_statuses(self):
        tx = self._create_transaction(flow="redirect")
        tx._handle_notification_data("payu_gpo", self._order_notification("PENDING"))
        self.assertEqual(tx.state, "pending")
        tx._handle_notification_data("payu_gpo", self._order_notification("COMPLETED"))
        self.assertEqual(tx.state, "done")
        self.assertEqual(tx.provider_reference, self.order_id)

    def test_canceled_order(self):
        tx = self._create_transaction(flow="redirect")
        tx._handle_notification_data("payu_gpo", self._order_notification("CANCELED"))
        self.assertEqual(tx.state, "cancel")

    def test_tokenization_after_completed_payment(self):
        tx = self._create_transaction(flow="redirect", tokenize=True)
        with (
            patch(f"{CLIENT}.get_trusted_merchant_token", return_value="BUYER"),
            patch(
                f"{CLIENT}.get_pay_methods",
                return_value={
                    "cardTokens": [
                        {
                            "value": "TOKC_OLD",
                            "status": "ACTIVE",
                            "cardNumberMasked": "4444",
                        },
                        {
                            "value": "TOKC_NEW",
                            "status": "ACTIVE",
                            "preferred": True,
                            "cardNumberMasked": "424242******4242",
                        },
                    ]
                },
            ),
        ):
            tx._handle_notification_data(
                "payu_gpo", self._order_notification("COMPLETED")
            )
        self.assertTrue(tx.token_id)
        self.assertEqual(tx.token_id.provider_ref, "TOKC_NEW")
        self.assertEqual(tx.token_id.payment_details, "4242")

    def test_offline_token_charge(self):
        token = self._create_token(provider_ref="TOKC_ABC")
        tx = self._create_transaction(
            flow="token", operation="offline", token_id=token.id
        )
        with patch(
            f"{CLIENT}.create_order", return_value={"orderId": "O2"}
        ) as create_order:
            tx._send_payment_request()
        payload = create_order.call_args.args[0]
        self.assertEqual(payload["recurring"], "STANDARD")
        self.assertEqual(
            payload["payMethods"]["payMethod"],
            {"type": "CARD_TOKEN", "value": "TOKC_ABC"},
        )
        self.assertNotIn("continueUrl", payload)
        self.assertEqual(tx.state, "pending")
        self.assertEqual(tx.provider_reference, "O2")

    def test_offline_charge_error_does_not_raise(self):
        token = self._create_token(provider_ref="TOKC_ABC")
        tx = self._create_transaction(
            flow="token", operation="offline", token_id=token.id
        )
        with patch(f"{CLIENT}.create_order", side_effect=PayuError("declined")):
            tx._send_payment_request()
        self.assertEqual(tx.state, "error")

    def test_refund(self):
        tx = self._create_transaction(
            flow="redirect", state="done", provider_reference=self.order_id
        )
        with patch(f"{CLIENT}.refund", return_value={}) as refund:
            refund_tx = tx._send_refund_request(amount_to_refund=10.0)
        self.assertEqual(refund.call_args.args[:2], (self.order_id, "1000"))
        self.assertEqual(refund_tx.state, "pending")
        # Shape of a sandbox refund notification.
        refund_tx._handle_notification_data(
            "payu_gpo",
            {
                "orderId": self.order_id,
                "extOrderId": tx.reference,
                "refund": {
                    "refundId": "5001592615",
                    "extRefundId": refund_tx.reference,
                    "amount": "1000",
                    "currencyCode": "PLN",
                    "status": "FINALIZED",
                    "reason": "refund",
                },
            },
        )
        self.assertEqual(refund_tx.state, "done")
        self.assertEqual(refund_tx.provider_reference, "5001592615")
        self.assertEqual(tx.provider_reference, self.order_id)
