import hashlib
import json
from unittest.mock import Mock, patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import JsonRpcException
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon

from ..controllers.main import PayuGpoController
from ..payu_client import PayuUnknownOutcome
from .common import SECOND_KEY, PayuGpoCommon

CLIENT = "odoo.addons.payment_payu_gpo.payu_client.PayuClient"
TX = "odoo.addons.payment_payu_gpo.models.payment_transaction.PaymentTransaction"


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

    def test_card_payment_takes_the_secure_form_tokens(self):
        """The Secure Form returns TOK_ for a card to save (MULTI) and TOKD_
        for a one-off payment (SINGLE), as seen on the sandbox."""
        for card_token in ("TOK_X", "TOKD_X"):
            tx = self._create_transaction(
                flow="direct", reference=f"payu-secure-form-{card_token}"
            )
            with patch(f"{TX}._payu_gpo_pay_with_card_token", return_value=None) as pay:
                self.assertEqual(self._pay_card(tx, card_token), {"redirect_url": None})
            self.assertEqual(pay.call_args.args[0], card_token)

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_card_payment_accepted_survives_an_unreadable_status(self):
        """PayU accepted the order, the status read right after fails: the
        request still ends with the payment pending, never rolled back to a
        draft (which the cancel route would take for a payment PayU never
        got)."""
        tx = self._create_transaction(flow="direct")
        with (
            patch(
                f"{CLIENT}.create_order",
                return_value={
                    "orderId": self.order_id,
                    "status": {"statusCode": "SUCCESS"},
                },
            ),
            patch(f"{CLIENT}.get_order", return_value={"orders": "COMPLETED"}),
        ):
            self.assertEqual(self._pay_card(tx), {"redirect_url": None})
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "pending")
        self.assertEqual(tx.provider_reference, self.order_id)

    @mute_logger("odoo.http")
    def test_card_to_save_needs_a_multi_use_token(self):
        """A card to save needs the Secure Form's MULTI token (TOK_): a
        one-off TOKD_ is refused before anything reaches PayU."""
        tx = self._create_transaction(flow="direct", tokenize=True)
        with (
            patch(f"{CLIENT}.create_order") as create_order,
            self.assertRaises(JsonRpcException),
        ):
            self._pay_card(tx, card_token="TOKD_X")
        create_order.assert_not_called()
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

    def test_card_and_cancel_routes_lock_the_payment(self):
        """Both routes lock the payment: a cancel never overlaps the card
        payment of the same draft, it waits and then finds it pending."""
        paid, canceled = (
            self._create_transaction(flow="direct", reference=reference)
            for reference in ("payu-lock-paid", "payu-lock-canceled")
        )
        with (
            patch(f"{TX}._payu_gpo_pay_with_card_token", return_value=None),
            patch.object(self.cr, "execute", wraps=self.cr.execute) as execute,
        ):
            self._pay_card(paid)
            self._cancel(canceled)
        for tx in (paid, canceled):
            locks = [
                call
                for call in execute.call_args_list
                if "FOR NO KEY UPDATE" in str(call.args[0])
                and len(call.args) > 1
                and list(call.args[1]) == [tx.id]
            ]
            self.assertEqual(len(locks), 1, tx.reference)

    @mute_logger("odoo.addons.payment_payu_gpo.models.payment_transaction")
    def test_cancel_after_the_card_route_changes_nothing(self):
        """Once the card route ran, the payment is no longer a draft, even
        without a PayU id (PayU did not answer): the cancel leaves it."""
        tx = self._create_transaction(flow="direct")
        with patch(f"{CLIENT}.create_order", side_effect=PayuUnknownOutcome("slow")):
            self.assertEqual(self._pay_card(tx), {"redirect_url": None})
        self._cancel(tx)
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "pending")
        self.assertFalse(tx.provider_reference)

    def _accepted_card_order(self):
        return {"orderId": self.order_id, "status": {"statusCode": "SUCCESS"}}

    def test_card_submission_is_checked_before_payu(self):
        """The calling module's check runs once the payment is locked, before
        the card reaches PayU; when it passes, the payment goes on."""
        calls = Mock()
        tx = self._create_transaction(flow="direct")
        with (
            patch(f"{TX}._payu_gpo_check_card_submission", calls.check),
            patch(
                f"{CLIENT}.create_order",
                calls.create_order,
            ),
            patch(f"{CLIENT}.get_order", return_value={"orders": []}),
        ):
            calls.create_order.return_value = self._accepted_card_order()
            self.assertEqual(self._pay_card(tx), {"redirect_url": None})
        self.assertEqual(
            [name for name, _args, _kwargs in calls.mock_calls],
            ["check", "create_order"],
        )
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "pending")

    @mute_logger("odoo.addons.payment_payu_gpo.controllers.main")
    def test_refused_card_submission_cancels_the_draft(self):
        """The check refuses: nothing reaches PayU, the draft is cancelled
        so that it blocks nothing, and the payment form shows why."""
        for i, error in enumerate(
            (
                ValidationError("This donation is already paid."),
                UserError("This donation is already paid."),
            )
        ):
            tx = self._create_transaction(
                flow="direct", reference=f"payu-refused-submission-{i}"
            )
            with (
                patch(f"{TX}._payu_gpo_check_card_submission", side_effect=error),
                patch(f"{CLIENT}.create_order") as create_order,
            ):
                result = self._pay_card(tx)
            create_order.assert_not_called()
            self.assertEqual(
                result,
                {"redirect_url": None, "error": "This donation is already paid."},
            )
            tx.invalidate_recordset()
            self.assertEqual(tx.state, "cancel")
            self.assertEqual(tx.state_message, "This donation is already paid.")

    @mute_logger("odoo.addons.payment_payu_gpo.controllers.main")
    def test_refused_card_submission_leaves_nothing_of_the_check(self):
        """The check runs in a savepoint: what it wrote, even written to the
        database before refusing, is undone, while the draft is still
        cancelled and the reason returned."""
        tx = self._create_transaction(flow="direct")
        refusal = ValidationError("This donation is already paid.")

        def write_then_refuse(transaction):
            transaction.payu_gpo_cardholder_name = "Written by the check"
            # Flushed: the UPDATE runs inside the savepoint before the refusal.
            transaction.flush_recordset()
            raise refusal

        with (
            patch(
                f"{TX}._payu_gpo_check_card_submission",
                autospec=True,
                side_effect=write_then_refuse,
            ),
            patch(f"{CLIENT}.create_order") as create_order,
        ):
            result = self._pay_card(tx)
        create_order.assert_not_called()
        self.assertEqual(result["error"], "This donation is already paid.")
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "cancel")
        self.assertFalse(tx.payu_gpo_cardholder_name)

    def test_card_submission_check_is_a_no_op_by_default(self):
        tx = self._create_transaction(flow="direct")
        with (
            patch(
                f"{CLIENT}.create_order", return_value=self._accepted_card_order()
            ) as create_order,
            patch(f"{CLIENT}.get_order", return_value={"orders": []}),
        ):
            self.assertEqual(self._pay_card(tx), {"redirect_url": None})
        create_order.assert_called_once()
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "pending")
        self.assertEqual(tx.provider_reference, self.order_id)
