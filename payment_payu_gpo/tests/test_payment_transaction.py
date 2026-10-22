import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment import utils as payment_utils

from .. import const
from ..payu_client import PayuError, PayuUnknownOutcome
from .common import PayuGpoCommon

CLIENT = "odoo.addons.payment_payu_gpo.payu_client.PayuClient"
TX = "odoo.addons.payment_payu_gpo.models.payment_transaction.PaymentTransaction"


@tagged("post_install", "-at_install")
class TestPaymentTransaction(PayuGpoCommon):
    def _card_response(self, status="SUCCESS", token="TOKC_NEW", **extra):
        response = {
            "orderId": self.order_id,
            "status": {"statusCode": status},
            **extra,
        }
        if token:
            response["payMethods"] = {
                "payMethod": {
                    "type": "CARD_TOKEN",
                    "value": token,
                    "card": {"number": "444433******1111"},
                }
            }
        return response

    def _completed(self):
        return {"orders": [self._order_notification("COMPLETED")["order"]]}

    # --- hosted page ----------------------------------------------------

    def test_redirect_creates_hosted_page_order(self):
        """The hosted page cannot store cards: no recurring flag there. Once
        PayU has the order, the payment is pending: the status reads watch
        it, and nothing takes it for an abandoned draft."""
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
        self.assertNotIn("cardOnFile", payload)
        self.assertNotIn("payMethods", payload)
        self.assertEqual(payload["totalAmount"], "111111")
        self.assertEqual(payload["currencyCode"], "PLN")
        self.assertEqual(payload["extOrderId"], tx.reference)
        self.assertEqual(values["url_params"], {"a": "1"})
        self.assertEqual(tx.provider_reference, self.order_id)
        self.assertEqual(tx.state, "pending")

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_hosted_order_without_answer_is_kept(self):
        """PayU may have created the order: the payment is kept, pending, so
        that the next attempt gets another reference, and the buyer goes to
        the status page instead of PayU's."""
        tx = self._create_transaction(flow="redirect")
        with patch(f"{CLIENT}.create_order", side_effect=PayuUnknownOutcome("slow")):
            values = tx._get_specific_rendering_values(None)
        self.assertEqual(values, {"api_url": "/payment/status", "url_params": {}})
        self.assertEqual(tx.state, "pending")
        self.assertFalse(tx.provider_reference)
        self.assertIn("did not answer", tx.state_message)

    def test_hosted_order_refused(self):
        """PayU refused the order: nothing to keep, the buyer sees why."""
        tx = self._create_transaction(flow="redirect")
        with (
            patch(f"{CLIENT}.create_order", side_effect=PayuError("refused")),
            self.assertRaises(ValidationError),
        ):
            tx._get_specific_rendering_values(None)

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

    def test_ext_customer_id_is_stable_and_per_partner(self):
        tx = self._create_transaction(flow="redirect")
        db_uuid = self.env["ir.config_parameter"].get_param("database.uuid")
        self.assertEqual(
            tx._payu_gpo_ext_customer_id(), f"odoo-{db_uuid}-{tx.partner_id.id}"
        )

    def test_inline_form_values_only_for_cards(self):
        values = json.loads(self.provider._payu_gpo_get_inline_form_values("card"))
        self.assertEqual(values["pos_id"], "300746")
        self.assertTrue(values["sdk_url"].endswith("/javascript/sdk"))
        self.assertFalse(self.provider._payu_gpo_get_inline_form_values("blik"))

    def test_direct_flow_access_token_not_logged(self):
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
        self.assertIn("payu_gpo_access_token", tx._get_specific_secret_keys())

    # --- card payments ----------------------------------------------------

    def test_saved_card_is_a_card_on_file_by_default(self):
        """Saving a card is not a subscription: cardOnFile, no recurring."""
        tx = self._create_transaction(flow="direct", tokenize=True)
        with (
            patch(
                f"{CLIENT}.create_order", return_value=self._card_response()
            ) as create_order,
            patch(f"{CLIENT}.get_order", return_value=self._completed()),
            patch(f"{CLIENT}.get_pay_methods") as get_pay_methods,
        ):
            redirect_url = tx._payu_gpo_pay_with_card_token(
                "TOK_ONCE", {"screenWidth": 1920}
            )
        payload = create_order.call_args.args[0]
        self.assertEqual(payload["cardOnFile"], "FIRST")
        self.assertNotIn("recurring", payload)
        self.assertEqual(
            payload["threeDsAuthentication"],
            {"browser": {"screenWidth": 1920}, "challengeRequested": "YES"},
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
        self.assertFalse(tx.token_id.payu_gpo_recurring)
        get_pay_methods.assert_not_called()

    def test_recurring_card(self):
        """The calling module says the card is for scheduled charges."""
        tx = self._create_transaction(flow="direct", tokenize=True)
        with (
            patch(f"{TX}._payu_gpo_card_is_recurring", return_value=True),
            patch(
                f"{CLIENT}.create_order", return_value=self._card_response()
            ) as create_order,
            patch(f"{CLIENT}.get_order", return_value=self._completed()),
        ):
            tx._payu_gpo_pay_with_card_token("TOK_ONCE")
        payload = create_order.call_args.args[0]
        self.assertEqual(payload["recurring"], "FIRST")
        self.assertNotIn("cardOnFile", payload)
        self.assertEqual(
            payload["threeDsAuthentication"],
            {"challengeRequested": "YES", "recurring": {"frequency": "30"}},
        )
        self.assertTrue(tx.token_id.payu_gpo_recurring)

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
                return_value=self._card_response(token=None),
            ) as create_order,
            patch(f"{CLIENT}.get_order", return_value=self._completed()),
        ):
            tx._payu_gpo_pay_with_card_token("TOK_ONCE", None, "  Anna   Nowak ")
        payload = create_order.call_args.args[0]
        self.assertEqual(
            payload["threeDsAuthentication"], {"cardholder": {"name": "Anna Nowak"}}
        )
        self.assertEqual(payload["buyer"]["firstName"], "Anna")
        self.assertEqual(payload["buyer"]["lastName"], "Nowak")
        self.assertEqual(tx.payu_gpo_cardholder_name, "Anna Nowak")

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_card_accepted_keeps_its_token_until_completed(self):
        """An accepted order whose status read fails keeps its reference and
        token, but saves no card before PayU completes it."""
        tx = self._create_transaction(flow="direct", tokenize=True)
        with (
            patch(f"{CLIENT}.create_order", return_value=self._card_response()),
            patch(f"{CLIENT}.get_order", side_effect=PayuError("timeout")),
        ):
            self.assertIsNone(tx._payu_gpo_pay_with_card_token("TOK_ONCE"))
        self.assertEqual(tx.state, "pending")
        self.assertEqual(tx.provider_reference, self.order_id)
        self.assertFalse(tx.token_id)
        self.assertEqual(tx.payu_gpo_card_token, "TOKC_NEW")
        tx._handle_notification_data("payu_gpo", self._order_notification("COMPLETED"))
        self.assertEqual(tx.token_id.provider_ref, "TOKC_NEW")

    def test_canceled_first_payment_saves_no_card(self):
        tx = self._create_transaction(flow="direct", tokenize=True)
        with (
            patch(f"{CLIENT}.create_order", return_value=self._card_response()),
            patch(
                f"{CLIENT}.get_order",
                return_value={
                    "orders": [self._order_notification("CANCELED")["order"]]
                },
            ),
        ):
            tx._payu_gpo_pay_with_card_token("TOK_ONCE")
        self.assertEqual(tx.state, "cancel")
        self.assertFalse(tx.token_id)

    def test_card_token_without_tokenization(self):
        tx = self._create_transaction(flow="direct")
        with (
            patch(
                f"{CLIENT}.create_order",
                return_value=self._card_response(token=None),
            ) as create_order,
            patch(f"{CLIENT}.get_order", return_value=self._completed()),
        ):
            tx._payu_gpo_pay_with_card_token("TOK_ONCE")
        self.assertNotIn("recurring", create_order.call_args.args[0])
        self.assertNotIn("cardOnFile", create_order.call_args.args[0])
        self.assertNotIn("threeDsAuthentication", create_order.call_args.args[0])
        self.assertEqual(tx.state, "done")
        self.assertFalse(tx.token_id)

    def test_3ds_saves_the_card_of_the_order(self):
        """After 3DS, the card saved is the one PayU returned with the order,
        never another card of the buyer, even a preferred one."""
        tx = self._create_transaction(flow="direct", tokenize=True)
        with patch(
            f"{CLIENT}.create_order",
            return_value=self._card_response(
                "WARNING_CONTINUE_3DS", redirectUri="https://3ds.example/"
            ),
        ):
            redirect_url = tx._payu_gpo_pay_with_card_token("TOK_ONCE")
        self.assertEqual(redirect_url, "https://3ds.example/")
        self.assertEqual(tx.state, "pending")
        self.assertFalse(tx.token_id)
        with patch(f"{CLIENT}.get_pay_methods") as get_pay_methods:
            tx._handle_notification_data(
                "payu_gpo", self._order_notification("COMPLETED")
            )
        self.assertEqual(tx.token_id.provider_ref, "TOKC_NEW")
        get_pay_methods.assert_not_called()

    def test_card_token_refused(self):
        tx = self._create_transaction(flow="direct")
        with patch(f"{CLIENT}.create_order", side_effect=PayuError("declined")):
            self.assertIsNone(tx._payu_gpo_pay_with_card_token("TOK_ONCE"))
        self.assertEqual(tx.state, "error")

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_no_answer_is_not_a_refusal(self):
        """A timeout may hide an accepted order: the payment stays pending,
        and PayU's notification (found by reference) settles it."""
        tx = self._create_transaction(flow="direct")
        with patch(f"{CLIENT}.create_order", side_effect=PayuUnknownOutcome("slow")):
            self.assertIsNone(tx._payu_gpo_pay_with_card_token("TOK_ONCE"))
        self.assertEqual(tx.state, "pending")
        self.assertFalse(tx.provider_reference)
        self.assertIn("did not answer", tx.state_message)
        tx._handle_notification_data("payu_gpo", self._order_notification("COMPLETED"))
        self.assertEqual(tx.state, "done")
        self.assertEqual(tx.provider_reference, self.order_id)

    def test_cvv_request_is_a_clear_failure(self):
        """The CVV redirectUri is an API URL, not a page for the buyer."""
        tx = self._create_transaction(flow="direct")
        with patch(
            f"{CLIENT}.create_order",
            return_value=self._card_response(
                "WARNING_CONTINUE_CVV",
                token=None,
                redirectUri="https://secure.payu.com/api/v2/token/token.json?refReqId=1",
            ),
        ):
            self.assertIsNone(tx._payu_gpo_pay_with_card_token("TOK_ONCE"))
        self.assertEqual(tx.state, "error")
        self.assertIn("CVV", tx.state_message)

    # --- notifications ------------------------------------------------------

    def test_order_statuses(self):
        tx = self._create_transaction(flow="redirect")
        tx._handle_notification_data("payu_gpo", self._order_notification("PENDING"))
        self.assertEqual(tx.state, "pending")
        tx._handle_notification_data("payu_gpo", self._order_notification("COMPLETED"))
        self.assertEqual(tx.state, "done")
        self.assertEqual(tx.provider_reference, self.order_id)

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_waiting_for_confirmation_tells_why(self):
        tx = self._create_transaction(flow="redirect")
        tx._handle_notification_data(
            "payu_gpo", self._order_notification("WAITING_FOR_CONFIRMATION")
        )
        self.assertEqual(tx.state, "pending")
        self.assertIn("automatic collection", tx.state_message)

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_waiting_for_confirmation_on_a_pending_payment(self):
        """The usual case: the payment is pending since PayU has the order."""
        tx = self._create_transaction(
            flow="redirect", state="pending", provider_reference=self.order_id
        )
        tx._handle_notification_data(
            "payu_gpo", self._order_notification("WAITING_FOR_CONFIRMATION")
        )
        self.assertEqual(tx.state, "pending")
        self.assertIn("automatic collection", tx.state_message)

    def test_canceled_order(self):
        tx = self._create_transaction(flow="redirect")
        tx._handle_notification_data("payu_gpo", self._order_notification("CANCELED"))
        self.assertEqual(tx.state, "cancel")

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_notification_of_another_payment_is_rejected(self):
        """Amount, currency and PayU order must be this payment's."""
        for change in (
            {"totalAmount": "100"},
            {"currencyCode": "EUR"},
            {"orderId": "ANOTHER-ORDER"},
        ):
            tx = self._create_transaction(
                flow="redirect",
                state="pending",
                provider_reference=self.order_id,
                reference=f"payu-mismatch-{next(iter(change))}",
            )
            notification = self._order_notification("COMPLETED", tx.reference)
            notification["order"].update(change)
            tx._handle_notification_data("payu_gpo", notification)
            self.assertEqual(tx.state, "error", change)

    def test_tokenization_matches_the_card_number(self):
        """Without a token in the order, the card is found by its number among
        the buyer's cards, never by PayU's "preferred" flag."""
        tx = self._create_transaction(flow="redirect", tokenize=True)
        tx.payu_gpo_card_mask = "424242******4242"
        pay_methods = {
            "cardTokens": [
                {
                    "value": "TOKC_OLD",
                    "status": "ACTIVE",
                    "preferred": True,
                    "cardNumberMasked": "444433******1111",
                },
                {
                    "value": "TOKC_NEW",
                    "status": "ACTIVE",
                    "cardNumberMasked": "424242******4242",
                },
            ]
        }
        with (
            patch(f"{CLIENT}.get_trusted_merchant_token", return_value="BUYER"),
            patch(f"{CLIENT}.get_pay_methods", return_value=pay_methods),
        ):
            tx._handle_notification_data(
                "payu_gpo", self._order_notification("COMPLETED")
            )
        self.assertEqual(tx.token_id.provider_ref, "TOKC_NEW")
        self.assertEqual(tx.token_id.payment_details, "4242")

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_tokenization_without_a_match_saves_nothing(self):
        tx = self._create_transaction(flow="redirect", tokenize=True)
        pay_methods = {
            "cardTokens": [
                {
                    "value": "TOKC_OLD",
                    "status": "ACTIVE",
                    "preferred": True,
                    "cardNumberMasked": "444433******1111",
                }
            ]
        }
        with (
            patch(f"{CLIENT}.get_trusted_merchant_token", return_value="BUYER"),
            patch(f"{CLIENT}.get_pay_methods", return_value=pay_methods),
        ):
            tx._handle_notification_data(
                "payu_gpo", self._order_notification("COMPLETED")
            )
        self.assertEqual(tx.state, "done")
        self.assertFalse(tx.token_id)
        self.assertTrue(tx.tokenize, "the cron tries again")

    # --- crons --------------------------------------------------------------

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_cron_retries_failed_tokenization(self):
        tx = self._create_transaction(flow="redirect", tokenize=True)
        tx.payu_gpo_card_mask = "424242******4242"
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
                {
                    "value": "TOKC_NEW",
                    "status": "ACTIVE",
                    "cardNumberMasked": "424242******4242",
                }
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

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_cron_gives_up_tokenization(self):
        tx = self._create_transaction(flow="redirect", tokenize=True, state="done")
        tx.last_state_change = "2020-01-01 00:00:00"
        with (
            patch(f"{CLIENT}.get_pay_methods") as get,
            patch(f"{TX}._payu_gpo_on_tokenization_abandoned") as abandoned,
        ):
            tx._cron_payu_gpo_retry_tokenization()
        get.assert_not_called()
        abandoned.assert_called_once()
        self.assertFalse(tx.tokenize)
        self.assertFalse(tx.token_id)

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
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
        txs.payu_gpo_card_mask = "424242******4242"
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

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_cron_error_does_not_stop_the_batch(self):
        """Any error is logged; the other payments of the batch are handled."""
        txs = self.env["payment.transaction"]
        for i in range(2):
            tx = self._create_transaction(
                flow="token",
                state="pending",
                provider_reference=f"O{i}",
                reference=f"payu-crash-{i}",
            )
            tx.last_state_change = fields.Datetime.now() - timedelta(minutes=30)
            txs |= tx
        with patch(
            f"{CLIENT}.get_order", side_effect=[ValueError("bug"), {"orders": []}]
        ) as get:
            txs._cron_payu_gpo_sync_pending()
        self.assertEqual(get.call_count, 2)
        self.assertTrue(all(txs.mapped("payu_gpo_sync_date")))

    @mute_logger(
        "odoo.addons.payment_payu_gpo.models.payment_transaction", "odoo.sql_db"
    )
    def test_cron_stamp_failure_does_not_stop_the_batch(self):
        """Writing the stamp can fail too, e.g. on a serialization error when
        PayU's notification of that payment commits during the batch: the
        payment is skipped, the database transaction stays usable, and the
        batch goes on."""
        txs = self.env["payment.transaction"]
        for i in range(2):
            tx = self._create_transaction(
                flow="token",
                state="pending",
                provider_reference=f"S{i}",
                reference=f"payu-stamp-{i}",
            )
            tx.last_state_change = fields.Datetime.now() - timedelta(minutes=30)
            txs |= tx
        self.env.flush_all()
        # The database refuses the first payment's stamp when it is flushed.
        self.env.cr.execute(
            """
            CREATE FUNCTION payu_gpo_test_refuse_stamp() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'could not serialize access';
            END $$;
            CREATE TRIGGER payu_gpo_test_refuse_stamp
            BEFORE UPDATE OF payu_gpo_sync_date ON payment_transaction
            FOR EACH ROW WHEN (NEW.id = %s)
            EXECUTE FUNCTION payu_gpo_test_refuse_stamp();
            """,
            [txs[0].id],
        )
        with patch(f"{CLIENT}.get_order", return_value={"orders": []}) as get:
            txs._cron_payu_gpo_sync_pending()
        self.assertEqual(get.call_args.args, ("S1",))
        self.assertEqual(get.call_count, 1)
        self.assertFalse(txs[0].payu_gpo_sync_date)
        self.assertTrue(txs[1].payu_gpo_sync_date)

    def test_cron_stops_at_its_time_budget(self):
        txs = self.env["payment.transaction"]
        for i in range(2):
            tx = self._create_transaction(
                flow="token",
                state="pending",
                provider_reference=f"T{i}",
                reference=f"payu-budget-{i}",
            )
            tx.last_state_change = fields.Datetime.now() - timedelta(minutes=30)
            txs |= tx
        with (
            patch.object(const, "CRON_TIME_BUDGET_SECONDS", -1),
            patch(f"{CLIENT}.get_order") as get,
        ):
            txs._cron_payu_gpo_sync_pending()
        get.assert_not_called()

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_status_page_reads_a_pending_payment(self):
        """The status page asks PayU itself, at most every few seconds."""
        tx = self._create_transaction(
            flow="redirect", state="pending", provider_reference=self.order_id
        )
        order = {"orders": [self._order_notification("CANCELED")["order"]]}
        with patch(f"{CLIENT}.get_order", side_effect=PayuError("slow")) as get:
            tx._payu_gpo_refresh_if_due()
            tx._payu_gpo_refresh_if_due()  # too soon: not asked again
        self.assertEqual(get.call_count, 1)
        self.assertEqual(tx.state, "pending")
        tx.payu_gpo_sync_date = fields.Datetime.now() - timedelta(minutes=1)
        with patch(f"{CLIENT}.get_order", return_value=order) as get:
            tx._payu_gpo_refresh_if_due()
            self.assertEqual(tx.state, "cancel")
            tx._payu_gpo_refresh_if_due()  # final: never asked again
        self.assertEqual(get.call_count, 1)

    def test_cron_syncs_pending_without_notification(self):
        """A pending payment whose notification never came is read from PayU."""
        tx = self._create_transaction(
            flow="token", state="pending", provider_reference=self.order_id
        )
        tx.last_state_change = fields.Datetime.now() - timedelta(minutes=30)
        with patch(f"{CLIENT}.get_order", return_value=self._completed()) as get:
            tx._cron_payu_gpo_sync_pending()
            self.assertEqual(tx.state, "done")
            # Done: never read again.
            tx._cron_payu_gpo_sync_pending()
        self.assertEqual(get.call_count, 1)

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
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

    def test_cron_gives_up_on_payments_payu_never_confirmed(self):
        """No PayU id and no notification after PayU's last retry (72 hours):
        the payment is set to error, flagged as an unknown outcome. Charges
        without the buyer, payments PayU may still notify and payments PayU
        has are left alone."""
        too_old = fields.Datetime.now() - timedelta(
            days=const.UNCONFIRMED_FAIL_DAYS, hours=1
        )
        unsent = self._create_transaction(
            flow="direct", state="pending", reference="payu-unsent"
        )
        token = self._create_token(provider_ref="TOKC_ABC")
        offline = self._create_transaction(
            flow="token",
            operation="offline",
            token_id=token.id,
            state="pending",
            reference="payu-unsent-offline",
        )
        known = self._create_transaction(
            flow="direct",
            state="pending",
            provider_reference=self.order_id,
            reference="payu-known",
        )
        (unsent | offline | known).last_state_change = too_old
        retried = self._create_transaction(
            flow="direct", state="pending", reference="payu-unsent-retried"
        )
        retried.last_state_change = fields.Datetime.now() - timedelta(hours=72)
        with patch(f"{CLIENT}.get_order", return_value={"orders": []}):
            self.env["payment.transaction"]._cron_payu_gpo_sync_pending()
        self.assertEqual(unsent.state, "error")
        self.assertIn("never confirmed", unsent.state_message)
        self.assertTrue(unsent.payu_gpo_unconfirmed)
        for tx in offline | known | retried:
            self.assertEqual(tx.state, "pending", tx.reference)
            self.assertFalse(tx.payu_gpo_unconfirmed, tx.reference)

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_cron_gives_up_on_each_unconfirmed_payment_on_its_own(self):
        """A payment that can't be set to error (e.g. a chatter post failing
        on a linked document) never stops the others."""
        txs = self.env["payment.transaction"]
        for i in range(2):
            txs |= self._create_transaction(
                flow="direct", state="pending", reference=f"payu-unsent-{i}"
            )
        txs.last_state_change = fields.Datetime.now() - timedelta(
            days=const.UNCONFIRMED_FAIL_DAYS, hours=1
        )
        Transaction = type(self.env["payment.transaction"])
        set_error = Transaction._set_error

        def failing_set_error(tx, *args, **kwargs):
            res = set_error(tx, *args, **kwargs)
            if tx == txs[0]:
                raise ValueError("chatter")
            return res

        with patch.object(
            Transaction, "_set_error", autospec=True, side_effect=failing_set_error
        ):
            self.env["payment.transaction"]._payu_gpo_fail_unconfirmed()
        self.assertEqual(txs[0].state, "pending")
        self.assertFalse(txs[0].payu_gpo_unconfirmed)
        self.assertEqual(txs[1].state, "error")
        self.assertTrue(txs[1].payu_gpo_unconfirmed)

    def test_cron_sync_pending_skips_refunds(self):
        """A refund's reference is a refund id: never read as an order."""
        tx = self._create_transaction(
            flow="redirect", state="done", provider_reference=self.order_id
        )
        with patch(f"{CLIENT}.refund", return_value={"refund": {"refundId": "R1"}}):
            refund_tx = tx._send_refund_request(amount_to_refund=10.0)
        refund_tx.last_state_change = fields.Datetime.now() - timedelta(minutes=30)
        with patch(f"{CLIENT}.get_order") as get:
            self.env["payment.transaction"]._cron_payu_gpo_sync_pending()
        get.assert_not_called()
        self.assertEqual(refund_tx.state, "pending")

    # --- disabled provider (neutralized database) ---------------------------

    def test_disabled_provider_never_calls_payu(self):
        tx = self._create_transaction(
            flow="token", state="pending", provider_reference=self.order_id
        )
        tx.last_state_change = fields.Datetime.now() - timedelta(minutes=30)
        self.provider.state = "disabled"
        with patch(f"{CLIENT}.get_order") as get:
            tx._cron_payu_gpo_sync_pending()
            with self.assertRaises(PayuError):
                self.provider._payu_gpo_client()
        get.assert_not_called()

    # --- token charges ------------------------------------------------------

    def test_offline_token_charge(self):
        for recurring, expected in (
            (True, {"recurring": "STANDARD"}),
            (False, {"cardOnFile": "STANDARD_MERCHANT"}),
        ):
            token = self._create_token(
                provider_ref=f"TOKC_{recurring}", payu_gpo_recurring=recurring
            )
            tx = self._create_transaction(
                flow="token",
                operation="offline",
                token_id=token.id,
                reference=f"payu-offline-{recurring}",
            )
            with patch(
                f"{CLIENT}.create_order", return_value={"orderId": "O2"}
            ) as create_order:
                tx._send_payment_request()
            payload = create_order.call_args.args[0]
            for key, value in expected.items():
                self.assertEqual(payload[key], value)
            self.assertEqual(len({"recurring", "cardOnFile"} & set(payload)), 1)
            self.assertEqual(
                payload["payMethods"]["payMethod"],
                {"type": "CARD_TOKEN", "value": f"TOKC_{recurring}"},
            )
            self.assertNotIn("continueUrl", payload)
            self.assertEqual(tx.state, "pending")
            self.assertEqual(tx.provider_reference, "O2")

    def test_refused_charge_without_the_buyer_is_an_error(self):
        """Nobody can give up a charge made without the buyer: PayU cancels
        it when the bank refuses it, whether the notification or the status
        read tells it."""
        token = self._create_token(provider_ref="TOKC_ABC")
        notified, read = (
            self._create_transaction(
                flow="token",
                operation="offline",
                token_id=token.id,
                state="pending",
                provider_reference=self.order_id,
                reference=reference,
            )
            for reference in ("payu-refused-notified", "payu-refused-read")
        )
        notified._handle_notification_data(
            "payu_gpo", self._order_notification("CANCELED", notified.reference)
        )
        self.assertEqual(notified.state, "error")
        self.assertIn("refused", notified.state_message)
        read.last_state_change = fields.Datetime.now() - timedelta(minutes=30)
        order = self._order_notification("CANCELED", read.reference)["order"]
        with patch(f"{CLIENT}.get_order", return_value={"orders": [order]}):
            read._cron_payu_gpo_sync_pending()
        self.assertEqual(read.state, "error")
        self.assertIn("refused", read.state_message)

    def test_charge_asking_for_the_cardholder_is_refused(self):
        """Without the buyer, nobody can authenticate: the charge is refused
        at once, and PayU's cancellation of the order changes nothing."""
        token = self._create_token(provider_ref="TOKC_ABC")
        tx = self._create_transaction(
            flow="token", operation="offline", token_id=token.id
        )
        with patch(
            f"{CLIENT}.create_order",
            return_value={
                "orderId": self.order_id,
                "status": {"statusCode": "WARNING_CONTINUE_3DS"},
                "redirectUri": "https://3ds.example/",
            },
        ):
            tx._send_payment_request()
        self.assertEqual(tx.state, "error")
        self.assertIn("refused", tx.state_message)
        self.assertEqual(tx.provider_reference, self.order_id)
        message = tx.state_message
        tx._handle_notification_data("payu_gpo", self._order_notification("CANCELED"))
        self.assertEqual(tx.state, "error")
        self.assertEqual(tx.state_message, message)

    def test_offline_charge_error_does_not_raise(self):
        token = self._create_token(provider_ref="TOKC_ABC")
        tx = self._create_transaction(
            flow="token", operation="offline", token_id=token.id
        )
        with patch(f"{CLIENT}.create_order", side_effect=PayuError("declined")):
            tx._send_payment_request()
        self.assertEqual(tx.state, "error")

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_offline_charge_without_answer_stays_pending(self):
        """Never "failed" while PayU may have charged: no second charge."""
        token = self._create_token(provider_ref="TOKC_ABC")
        tx = self._create_transaction(
            flow="token", operation="offline", token_id=token.id
        )
        with patch(f"{CLIENT}.create_order", side_effect=PayuUnknownOutcome("slow")):
            tx._send_payment_request()
        self.assertEqual(tx.state, "pending")

    def test_saved_card_not_charged_with_the_buyer_present(self):
        token = self._create_token(provider_ref="TOKC_ABC")
        tx = self._create_transaction(
            flow="token", operation="online_token", token_id=token.id
        )
        with (
            patch(f"{CLIENT}.create_order") as create_order,
            self.assertRaises(UserError),
        ):
            tx._send_payment_request()
        create_order.assert_not_called()
        self.assertFalse(
            self.env["payment.token"]._get_available_tokens(
                self.provider.ids, token.partner_id.id
            )
        )
        self.assertEqual(
            self.env["payment.token"]._get_available_tokens(
                self.provider.ids, token.partner_id.id, is_validation=True
            ),
            token,
        )

    def test_no_card_validation(self):
        """Saving a card without paying would need a zero-amount order."""
        args = (self.company.id, self.partner.id, 0.0)
        self.assertNotIn(
            self.provider,
            self.env["payment.provider"]._get_compatible_providers(
                *args, is_validation=True
            ),
        )
        self.assertIn(
            self.provider,
            self.env["payment.provider"]._get_compatible_providers(
                self.company.id,
                self.partner.id,
                self.amount,
                currency_id=self.currency.id,
            ),
        )

    def test_card_validation_refused_before_calling_payu(self):
        """A page that picks the provider itself, without asking for the
        compatible ones, still never sends PayU a zero-amount order."""
        tx = self._create_transaction(
            flow="redirect", operation="validation", amount=0.0, tokenize=True
        )
        with (
            patch(
                f"{CLIENT}.create_order",
                return_value={
                    "orderId": self.order_id,
                    "redirectUri": "https://pay.example/",
                },
            ) as create_order,
            self.assertRaises(UserError),
        ):
            tx._get_processing_values()
        create_order.assert_not_called()

    # --- refunds ------------------------------------------------------------

    def test_refund(self):
        tx = self._create_transaction(
            flow="redirect", state="done", provider_reference=self.order_id
        )
        with patch(
            f"{CLIENT}.refund", return_value={"refund": {"refundId": "5001592615"}}
        ) as refund:
            refund_tx = tx._send_refund_request(amount_to_refund=10.0)
        self.assertEqual(refund.call_args.args[:2], (self.order_id, "1000"))
        self.assertEqual(refund_tx.state, "pending")
        self.assertEqual(refund_tx.provider_reference, "5001592615")
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

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_refund_without_answer_stays_pending(self):
        tx = self._create_transaction(
            flow="redirect", state="done", provider_reference=self.order_id
        )
        with patch(f"{CLIENT}.refund", side_effect=PayuUnknownOutcome("slow")):
            refund_tx = tx._send_refund_request(amount_to_refund=10.0)
        self.assertEqual(refund_tx.state, "pending")
