import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from odoo.addons.payment import utils as payment_utils

from .. import const
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
        # A database may already have one set (a dev tunnel).
        self.env["ir.config_parameter"].set_param(
            "payment_payu_gpo.notify_base_url", False
        )
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

    def test_buyer_names_extension_point(self):
        """Empty buyer names are left out of the order, not sent blank."""
        tx = self._create_transaction(flow="redirect")
        self.assertEqual(
            tx._payu_gpo_buyer_names(),
            payment_utils.split_partner_name(tx.partner_name),
        )
        client = tx.provider_id._payu_gpo_client()
        with patch.object(type(tx), "_payu_gpo_buyer_names", return_value=("", "")):
            payload = client.build_order_payload(**tx._payu_gpo_order_values())
        self.assertNotIn("firstName", payload["buyer"])
        self.assertNotIn("lastName", payload["buyer"])
        self.assertEqual(payload["buyer"]["email"], tx.partner_email)

    def test_card_token_sends_cardholder_name(self):
        """The name typed next to the Secure Form goes to 3DS and the buyer."""
        tx = self._create_transaction(flow="direct", tokenize=False)
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
            tx._payu_gpo_pay_with_card_token("TOK_ONCE", None, "  Anna   Nowak ")
        payload = create_order.call_args.args[0]
        self.assertEqual(
            payload["threeDsAuthentication"], {"cardholder": {"name": "Anna Nowak"}}
        )
        self.assertEqual(payload["buyer"]["firstName"], "Anna")
        self.assertEqual(payload["buyer"]["lastName"], "Nowak")
        self.assertEqual(tx.payu_gpo_cardholder_name, "Anna Nowak")

    def test_card_token_accepted_survives_failed_refresh(self):
        """The accepted order keeps its reference and token; the webhook settles it."""
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
            ),
            patch(f"{CLIENT}.get_order", side_effect=PayuError("timeout")),
        ):
            self.assertIsNone(tx._payu_gpo_pay_with_card_token("TOK_ONCE"))
        self.assertEqual(tx.state, "pending")
        self.assertEqual(tx.provider_reference, self.order_id)
        self.assertEqual(tx.token_id.provider_ref, "TOKC_NEW")

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

    def test_cron_retries_failed_tokenization(self):
        tx = self._create_transaction(flow="redirect", tokenize=True)
        with patch(
            f"{CLIENT}.get_trusted_merchant_token", side_effect=PayuError("down")
        ):
            tx._handle_notification_data(
                "payu_gpo", self._order_notification("COMPLETED")
            )
        self.assertEqual(tx.state, "done")
        self.assertFalse(tx.token_id)
        pay_methods = {
            "cardTokens": [
                {"value": "TOKC_NEW", "status": "ACTIVE", "cardNumberMasked": "4242"}
            ]
        }
        with (
            patch(f"{CLIENT}.get_trusted_merchant_token", return_value="BUYER"),
            patch(f"{CLIENT}.get_pay_methods", return_value=pay_methods) as get,
        ):
            tx._cron_payu_gpo_retry_tokenization()
            self.assertEqual(tx.token_id.provider_ref, "TOKC_NEW")
            self.assertFalse(tx.tokenize)
            # Idempotent: a saved card is never fetched again.
            tx._cron_payu_gpo_retry_tokenization()
        self.assertEqual(get.call_count, 1)

    def test_cron_gives_up_tokenization(self):
        tx = self._create_transaction(flow="redirect", tokenize=True, state="done")
        tx.last_state_change = "2020-01-01 00:00:00"
        with patch(f"{CLIENT}.get_pay_methods") as get:
            tx._cron_payu_gpo_retry_tokenization()
        get.assert_not_called()
        self.assertFalse(tx.tokenize)
        self.assertFalse(tx.token_id)

    def test_cron_retries_in_batches(self):
        """A failing payment is tried once per run and never starves the others."""
        txs = self.env["payment.transaction"]
        for i in range(3):
            txs |= self._create_transaction(
                flow="redirect",
                tokenize=True,
                state="done",
                reference=f"payu-batch-{i}",
            )
        with (
            patch.object(const, "TOKENIZATION_RETRY_BATCH", 2),
            patch(
                f"{CLIENT}.get_trusted_merchant_token", side_effect=PayuError("down")
            ) as get,
        ):
            txs._cron_payu_gpo_retry_tokenization()
            self.assertEqual(get.call_count, 2)
            # Next batch: only the payment not tried yet.
            txs._cron_payu_gpo_retry_tokenization()
            self.assertEqual(get.call_count, 3)
            # All tried in this run: nothing left until the retry delay.
            txs._cron_payu_gpo_retry_tokenization()
            self.assertEqual(get.call_count, 3)
        self.assertTrue(all(txs.mapped("payu_gpo_token_retry_date")))
        self.assertTrue(all(txs.mapped("tokenize")))

    def test_cron_syncs_pending_without_notification(self):
        """A pending payment whose notification never came is read from PayU."""
        tx = self._create_transaction(
            flow="token", state="pending", provider_reference=self.order_id
        )
        tx.last_state_change = fields.Datetime.now() - timedelta(minutes=30)
        order = {"orders": [self._order_notification("COMPLETED")["order"]]}
        with patch(f"{CLIENT}.get_order", return_value=order) as get:
            tx._cron_payu_gpo_sync_pending()
            self.assertEqual(tx.state, "done")
            # Done: never read again.
            tx._cron_payu_gpo_sync_pending()
        self.assertEqual(get.call_count, 1)

    def test_cron_sync_pending_skips_recent_old_and_failing(self):
        recent = self._create_transaction(
            flow="token", state="pending", provider_reference="R", reference="r1"
        )
        old = self._create_transaction(
            flow="token", state="pending", provider_reference="O", reference="o1"
        )
        old.last_state_change = "2020-01-01 00:00:00"
        failing = self._create_transaction(
            flow="token", state="pending", provider_reference="F", reference="f1"
        )
        failing.last_state_change = fields.Datetime.now() - timedelta(minutes=30)
        with patch(f"{CLIENT}.get_order", side_effect=PayuError("down")) as get:
            (recent | old | failing)._cron_payu_gpo_sync_pending()
            # Only the failing one is read; not again before the delay.
            (recent | old | failing)._cron_payu_gpo_sync_pending()
        self.assertEqual(get.call_count, 1)
        self.assertEqual(failing.state, "pending")
        self.assertTrue(failing.payu_gpo_sync_date)

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
