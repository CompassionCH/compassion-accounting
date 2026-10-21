##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
"""Odoo 18 binding of the PayU GPO client.

The notification hooks of Odoo 18 are thin wrappers around the _payu_gpo_*
helpers below, which hold the logic (see ROADMAP.md for the Odoo 19/20 port).

Extension points for other PayU methods (e.g. BLIK recurring, PAYID tokens):
_payu_gpo_create_direct_order, _payu_gpo_token_payment_values and
_payu_gpo_token_values_from_pay_methods; for the calling module:
_payu_gpo_buyer_names, _payu_gpo_card_is_recurring and
_payu_gpo_on_tokenization_abandoned.
"""

import logging
import time
from datetime import timedelta
from urllib.parse import parse_qsl, urlsplit

from werkzeug import urls

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.payment import utils as payment_utils

from .. import const
from ..controllers.main import PayuGpoController
from ..payu_client import PayuError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    payu_gpo_cardholder_name = fields.Char(
        string="PayU cardholder name",
        readonly=True,
        copy=False,
        help="Name on the card, as typed in the card form: sent to PayU for 3-D"
        " Secure and as the buyer's name.",
    )
    payu_gpo_card_token = fields.Char(
        string="PayU card token",
        readonly=True,
        copy=False,
        groups="base.group_system",
        help="Multi-use TOKC_ token PayU returned for the card of this payment;"
        " saved as a payment token once the payment is completed.",
    )
    payu_gpo_card_mask = fields.Char(
        string="PayU card number",
        readonly=True,
        copy=False,
        help="Masked number of the card of this payment, used to find its token"
        " among the buyer's cards when PayU did not return it.",
    )
    payu_gpo_recurring = fields.Boolean(
        string="PayU recurring card",
        readonly=True,
        copy=False,
        help="The card is saved for scheduled recurring charges (recurring=FIRST)"
        " rather than as a card on file.",
    )
    payu_gpo_sync_date = fields.Datetime(
        string="PayU status read on",
        readonly=True,
        copy=False,
        help="Last time the status of this pending payment was read from PayU"
        " (cron or payment status page).",
    )
    payu_gpo_token_retry_date = fields.Datetime(
        string="PayU card save retried on",
        readonly=True,
        copy=False,
        help="Last time the cron tried to save the card of this payment.",
    )

    def _get_specific_secret_keys(self):
        """The access token of the card route is never logged."""
        if self.provider_code == const.PROVIDER_CODE:
            return {"payu_gpo_access_token": None}.keys()
        return super()._get_specific_secret_keys()

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
        redirect_uri = order.get("redirectUri")
        if not order.get("orderId") or not redirect_uri:
            raise ValidationError(_("PayU did not return a payment page."))
        self.provider_reference = order["orderId"]
        # The order exists at PayU: from now on PayU owns the outcome, and the
        # status reads (cron, status page) watch this payment.
        self._set_pending()
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

    def _payu_gpo_pay_with_card_token(
        self, card_token, browser=None, cardholder_name=None, card_mask=None
    ):
        """Charge the TOK_ token the Secure Form returned.

        :param dict browser: threeDsAuthentication.browser data; without it
                             PayU can only attempt 3DS, which issuers refuse
                             for a first recurring payment
        :param str cardholder_name: name on the card typed by the buyer (the
                             Secure Form does not ask it): 3DS data, and the
                             buyer's name PayU sends back in its notification
        :param str card_mask: masked card number from the Secure Form, to find
                             the card among the buyer's ones if PayU does not
                             return its token
        :return: the URL where the buyer must authenticate (3DS), or None
        """
        cardholder_name = " ".join((cardholder_name or "").split())[:100]
        values = {}
        if cardholder_name:
            values["payu_gpo_cardholder_name"] = cardholder_name
        if card_mask:
            values["payu_gpo_card_mask"] = str(card_mask)[:32]
        three_ds = {"browser": browser} if browser else {}
        if cardholder_name:
            three_ds["cardholder"] = {"name": cardholder_name}
        recurring = card_on_file = None
        if self.tokenize:
            # Strong authentication when storing the card.
            three_ds["challengeRequested"] = "YES"
            if self._payu_gpo_card_is_recurring():
                values["payu_gpo_recurring"] = True
                recurring = "FIRST"
                three_ds["recurring"] = {"frequency": "30"}
            else:
                card_on_file = "FIRST"
        if values:
            self.write(values)
        return self._payu_gpo_create_direct_order(
            {"type": "CARD_TOKEN", "value": card_token},
            recurring=recurring,
            card_on_file=card_on_file,
            three_ds=three_ds,
        )

    def _payu_gpo_card_is_recurring(self):
        """Whether the card saved by this payment is for scheduled recurring
        charges (subscription, monthly donation...), registered at PayU and
        at the bank as such (recurring=FIRST, then STANDARD).

        Otherwise the card is saved as a card on file (cardOnFile=FIRST): the
        buyer only asked to keep it, and later charges are unscheduled.
        Extension point for the module that knows what the card is for.
        """
        return False

    def _payu_gpo_create_direct_order(
        self, pay_method, recurring=None, card_on_file=None, three_ds=None
    ):
        """Create an order paid with pay_method, the buyer being on the site.

        Extension point for other direct-flow methods (e.g. a BLIK code).

        :return: the URL where the buyer must authenticate, or None
        """
        client = self.provider_id._payu_gpo_client()
        payload = client.build_order_payload(
            recurring=recurring,
            card_on_file=card_on_file,
            pay_method=pay_method,
            three_ds=three_ds,
            **self._payu_gpo_order_values(with_continue_url=True),
        )
        try:
            response = client.create_order(payload)
        except PayuError as e:
            self._payu_gpo_set_failed(e)
            return None
        self.provider_reference = response.get("orderId")
        self._payu_gpo_store_card_token(response)
        status_code = response.get("status", {}).get("statusCode", "")
        if status_code == "WARNING_CONTINUE_CVV":
            # PayU then needs the CVV through the Secure Form, not a page.
            # Without it the order is never paid, and PayU cancels it.
            self._set_error(
                _(
                    "Your bank asked for an extra security check (CVV code)"
                    " that this payment form can't handle yet. No money has"
                    " been taken. Please try again, and if it happens again,"
                    " contact us."
                )
            )
            return None
        # The token is saved only once the order is completed (notification
        # or status read): PayU refuses later charges on a failed first one.
        self._set_pending()
        if status_code.startswith("WARNING"):
            # 3DS: the buyer comes back through the return route.
            return response.get("redirectUri")
        try:
            self._payu_gpo_refresh_from_api()
        except PayuError as e:
            _logger.warning("PayU: could not refresh %s: %s", self.reference, e)
        return None

    def _payu_gpo_set_failed(self, error):
        """A request to create an order failed: a refusal when PayU says so,
        otherwise the order may exist and its notification will settle it."""
        if error.definitive:
            self._set_error(_("PayU: %s", error))
        else:
            _logger.warning(
                "PayU: no answer for %s, waiting for its notification: %s",
                self.reference,
                error,
            )
            self._set_pending(
                _(
                    "PayU did not answer (%s). The payment may have been made:"
                    " PayU's notification will update it.",
                    error,
                )
            )

    def _payu_gpo_store_card_token(self, response):
        """Keep the multi-use token PayU returns with the order, 3DS or not.

        Extension point for other token types (e.g. BLIK PAYID).
        """
        pay_method = response.get("payMethods", {}).get("payMethod", {})
        if not self.tokenize or not pay_method.get("value", "").startswith("TOKC_"):
            return
        values = {"payu_gpo_card_token": pay_method["value"]}
        number = pay_method.get("card", {}).get("number")
        if number:
            values["payu_gpo_card_mask"] = number
        self.sudo().write(values)

    def _payu_gpo_refresh_from_api(self):
        """Read the order status from PayU (no webhook needed, e.g. on dev)."""
        if not self.provider_reference:
            return
        order = self.provider_id._payu_gpo_client().get_order(self.provider_reference)
        for payu_order in order.get("orders", []):
            self._handle_notification_data(const.PROVIDER_CODE, {"order": payu_order})

    def _payu_gpo_order_values(self, with_continue_url=False):
        base_url = self.provider_id.get_base_url()
        first_name, last_name = self._payu_gpo_buyer_names()
        values = {
            "ext_order_id": self.reference,
            "description": self.reference,
            "amount_minor": self._payu_gpo_minor(self.amount),
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
                "language": (self.partner_lang or self.env.lang or "en")[:2],
            },
        }
        if with_continue_url:
            values["continue_url"] = urls.url_join(
                base_url, PayuGpoController._return_url
            )
        return values

    def _payu_gpo_minor(self, amount):
        return str(payment_utils.to_minor_currency_units(amount, self.currency_id))

    def _payu_gpo_buyer_names(self):
        """First and last name of the buyer sent to PayU: the name on the
        card when the buyer typed one, else the partner's name.

        Extension point: a module whose partners can be known by email only
        returns ("", "") for them, so that PayU asks the name instead of
        showing a placeholder (empty values are not sent).
        """
        name = (self.payu_gpo_cardholder_name or self.partner_name or "").strip()
        return payment_utils.split_partner_name(name) if name else ("", "")

    def _payu_gpo_notify_base_url(self):
        """Public URL PayU sends notifications to, when it differs from the
        base URL (reverse proxy, or a tunnel exposing only the webhook)."""
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("payment_payu_gpo.notify_base_url")
        )

    def _payu_gpo_ext_customer_id(self):
        """Stable buyer identifier PayU attaches the stored card tokens to:
        one per paying partner, kept across database renames and restores."""
        db_uuid = self.env["ir.config_parameter"].sudo().get_param("database.uuid")
        return f"odoo-{db_uuid}-{self.partner_id.id}"

    # --- outgoing: merchant-initiated token charge --------------------------

    def _send_payment_request(self):
        """Charge the saved PayU token, no buyer involvement (operation
        offline). The outcome arrives asynchronously through the webhook.

        Saved PayU cards are not offered to a buyer on the site (see
        payment.token): charging one with the buyer present needs the
        cardholder flags and 3DS handling of a customer-initiated payment.
        """
        super()._send_payment_request()
        if self.provider_code != const.PROVIDER_CODE:
            return
        if not self.token_id:
            raise UserError(_("PayU: the transaction is not linked to a token."))
        if self.operation != "offline":
            raise UserError(
                _("PayU: a saved card can only be charged without the buyer.")
            )

        client = self.provider_id._payu_gpo_client()
        payload = client.build_order_payload(
            **self._payu_gpo_token_payment_values(),
            **self._payu_gpo_order_values(),
        )
        try:
            order = client.create_order(payload)
        except PayuError as e:
            self._payu_gpo_set_failed(e)
            return
        self.provider_reference = order.get("orderId")
        status_code = order.get("status", {}).get("statusCode", "")
        if status_code.startswith("WARNING"):
            # The bank wants the cardholder (3DS, CVV): PayU will cancel it.
            self._set_pending(
                _(
                    "PayU asked for the cardholder (%s): the charge will fail.",
                    status_code,
                )
            )
            return
        self._set_pending()

    def _payu_gpo_token_payment_values(self):
        """recurring or cardOnFile and pay_method of a merchant-initiated token
        charge, as the card was saved.

        Extension point for other token types (e.g. BLIK PAYID).
        """
        values = {
            "pay_method": {"type": "CARD_TOKEN", "value": self.token_id.provider_ref},
        }
        if self.token_id.payu_gpo_recurring:
            values["recurring"] = "STANDARD"
        else:
            values["card_on_file"] = "STANDARD_MERCHANT"
        return values

    def _send_refund_request(self, amount_to_refund=None):
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if self.provider_code != const.PROVIDER_CODE:
            return refund_tx
        client = self.provider_id._payu_gpo_client()
        try:
            response = client.refund(
                self.provider_reference,
                refund_tx._payu_gpo_minor(-refund_tx.amount),
                description=refund_tx.reference,
                ext_refund_id=refund_tx.reference,
            )
        except PayuError as e:
            refund_tx._payu_gpo_set_failed(e)
            return refund_tx
        refund_id = (response.get("refund") or {}).get("refundId")
        if refund_id:
            refund_tx.provider_reference = refund_id
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
            mismatch = self._payu_gpo_mismatch(
                refund, refund.get("refundId"), -self.amount
            )
            if mismatch:
                self._payu_gpo_reject(mismatch)
                return
            if refund.get("refundId"):
                self.provider_reference = refund["refundId"]
            status = refund.get("status")
            if status == "FINALIZED":
                self._set_done()
            elif status == "CANCELED":
                self._set_canceled(_("PayU canceled the refund."))
            return

        order = notification_data.get("order") or {}
        mismatch = self._payu_gpo_mismatch(
            order, order.get("orderId"), self.amount, amount_key="totalAmount"
        )
        if mismatch:
            self._payu_gpo_reject(mismatch)
            return
        if order.get("orderId"):
            self.provider_reference = order["orderId"]
        status = order.get("status")
        if status == "WAITING_FOR_CONFIRMATION":
            # Authorized, waiting to be captured: only happens when automatic
            # collection is off for this payment method, and PayU then cancels
            # the order after a few days.
            _logger.warning(
                "PayU: %s waits for a capture: enable automatic collection"
                " (auto-receive) for its payment method on the POS.",
                self.reference,
            )
            message = _(
                "PayU holds this payment until it is captured: automatic"
                " collection must be enabled on the PayU point of sale."
            )
            if self.state == "pending":
                # _set_pending only leaves draft: it would drop the message.
                self.state_message = message
            else:
                self._set_pending(message)
        elif status in const.STATUS_MAPPING["pending"]:
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

    def _payu_gpo_mismatch(self, data, payu_id, amount, amount_key="amount"):
        """Why the order or refund PayU reports is not this transaction's, or
        "" when it is: the signature proves who sent it, not what about."""
        if payu_id and self.provider_reference and payu_id != self.provider_reference:
            return _(
                "PayU reported %(payu)s, this payment is %(ours)s.",
                payu=payu_id,
                ours=self.provider_reference,
            )
        currency = data.get("currencyCode")
        if currency and currency != self.currency_id.name:
            return _("PayU reported the currency %s.", currency)
        payu_amount = data.get(amount_key)
        if payu_amount and str(payu_amount) != self._payu_gpo_minor(amount):
            return _("PayU reported the amount %s (in minor units).", payu_amount)
        return ""

    def _payu_gpo_reject(self, reason):
        _logger.warning(
            "PayU: notification for %s rejected: %s", self.reference, reason
        )
        self._set_error(_("PayU: %s", reason))

    def _payu_gpo_tokenize(self):
        """Save the card of this completed payment, once."""
        if self.token_id or not self.tokenize:
            return
        # Read the card from PayU first: no lock is held during the calls.
        token_values = self._payu_gpo_extract_token_values()
        if not token_values:
            _logger.warning("PayU: no token found after payment %s", self.reference)
            return
        # The return route, the webhook and the retry cron may race. Locking
        # the row makes a concurrent saver fail on a serialization error (and
        # be retried by Odoo) instead of both creating a token.
        self.env.cr.execute(
            "SELECT 1 FROM payment_transaction WHERE id = %s FOR NO KEY UPDATE",
            [self.id],
        )
        self.invalidate_recordset(["token_id", "tokenize"])
        if self.token_id or not self.tokenize:
            return
        token = self.env["payment.token"].create(
            {
                "provider_id": self.provider_id.id,
                "payment_method_id": self.payment_method_id.id,
                "partner_id": self.partner_id.id,
                "payu_gpo_recurring": self.payu_gpo_recurring,
                **token_values,
            }
        )
        self.write({"token_id": token.id, "tokenize": False})

    def _payu_gpo_refresh_if_due(self):
        """Read the status of a pending payment from PayU, for the payment
        status page: PayU's notification may be late or lost (Odoo restarted,
        tunnel down), and the page would then poll forever. At most once
        every SYNC_POLL_SECONDS per payment; an API error is only logged, the
        page simply asks again.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        due = not self.payu_gpo_sync_date or (
            self.payu_gpo_sync_date < now - timedelta(seconds=const.SYNC_POLL_SECONDS)
        )
        if (
            self.provider_code != const.PROVIDER_CODE
            or self.state != "pending"
            or not self.provider_reference
            or not due
        ):
            return
        self.payu_gpo_sync_date = now
        try:
            self._payu_gpo_refresh_from_api()
        except PayuError as e:
            _logger.warning(
                "PayU: could not read the status of %s: %s", self.reference, e
            )

    def _payu_gpo_cron_domain(self):
        """PayU payments the crons may work on: never those of a disabled
        provider (a neutralized copy of production, among others)."""
        return [
            ("provider_code", "=", const.PROVIDER_CODE),
            ("provider_id.state", "in", ("enabled", "test")),
        ]

    def _payu_gpo_cron_run(self, txs, total, stamp_field, work):
        """Run work on each transaction of a cron batch, then report progress.

        Each payment is stamped first, then handled in a savepoint: a failing
        one is logged and never rolls back the others. The batch stops after
        CRON_TIME_BUDGET_SECONDS, before Odoo's time limit kills it unsaved.
        """
        deadline = time.monotonic() + const.CRON_TIME_BUDGET_SECONDS
        done = 0
        for tx in txs:
            if time.monotonic() > deadline:
                break
            tx[stamp_field] = fields.Datetime.now()
            done += 1
            try:
                with self.env.cr.savepoint():
                    work(tx)
            except PayuError as e:
                _logger.warning("PayU: %s: %s", tx.reference, e)
            except Exception:
                _logger.exception("PayU: could not handle %s", tx.reference)
        self.env["ir.cron"]._notify_progress(done=done, remaining=total - done)

    def _cron_payu_gpo_sync_pending(self):
        """Read from PayU the status of the payments still pending.

        The final status of a payment comes with PayU's notification; a
        payment charged with a saved card has no return from PayU at all. If
        the notification is lost (Odoo down or not reachable), the payment
        would stay pending although PayU completed or cancelled it.

        Each payment is read at most once per delay, the least recently read
        first, by batches committed through the progress API.
        """
        self._payu_gpo_fail_unconfirmed()
        now = fields.Datetime.now()
        delay = timedelta(minutes=const.SYNC_PENDING_DELAY_MINUTES)
        domain = self._payu_gpo_cron_domain() + [
            ("state", "=", "pending"),
            ("provider_reference", "!=", False),
            # A refund's reference is a refund id, not an order id.
            ("operation", "!=", "refund"),
            ("last_state_change", "<", now - delay),
            ("last_state_change", ">", now - timedelta(days=const.SYNC_PENDING_DAYS)),
            "|",
            ("payu_gpo_sync_date", "=", False),
            ("payu_gpo_sync_date", "<", now - delay),
        ]
        txs = self.search(
            domain,
            order="payu_gpo_sync_date asc nulls first, id",
            limit=const.SYNC_PENDING_BATCH,
        )
        self._payu_gpo_cron_run(
            txs,
            self.search_count(domain),
            "payu_gpo_sync_date",
            lambda tx: tx._payu_gpo_refresh_from_api(),
        )

    def _payu_gpo_fail_unconfirmed(self):
        """Fail the payments and refunds PayU never confirmed: sent without
        an answer, they have no PayU id, and no notification came.

        Charges Odoo makes on its own with a saved card are skipped: the
        module that started them decides when they fail."""
        before = fields.Datetime.now() - timedelta(days=const.UNCONFIRMED_FAIL_DAYS)
        txs = self.search(
            self._payu_gpo_cron_domain()
            + [
                ("state", "=", "pending"),
                ("provider_reference", "=", False),
                ("operation", "!=", "offline"),
                ("last_state_change", "<", before),
            ]
        )
        for tx in txs:
            tx._set_error(
                _(
                    "PayU never confirmed %s. Check the PayU panel for this"
                    " reference before trying again.",
                    tx.reference,
                )
            )

    def _cron_payu_gpo_retry_tokenization(self):
        """Save the cards that completed payments could not save.

        After 3DS the token may have to be read from PayU once the order is
        completed; if that call fails, nothing else would try again. Give up
        after a few days: the buyer must then enter the card again.

        Works in batches committed by the cron (progress API), oldest attempt
        first, so a PayU outage neither loses saved cards nor starves the
        other payments.
        """
        now = fields.Datetime.now()
        retry_before = now - timedelta(minutes=const.TOKENIZATION_RETRY_DELAY_MINUTES)
        domain = self._payu_gpo_cron_domain() + [
            ("state", "=", "done"),
            ("tokenize", "=", True),
            ("token_id", "=", False),
            "|",
            ("payu_gpo_token_retry_date", "=", False),
            ("payu_gpo_token_retry_date", "<", retry_before),
        ]
        txs = self.search(
            domain,
            order="payu_gpo_token_retry_date asc nulls first, id",
            limit=const.TOKENIZATION_RETRY_BATCH,
        )
        give_up_before = now - timedelta(days=const.TOKENIZATION_RETRY_DAYS)

        def retry(tx):
            if tx.last_state_change < give_up_before:
                tx.tokenize = False
                tx._payu_gpo_on_tokenization_abandoned()
            else:
                tx._payu_gpo_tokenize()

        self._payu_gpo_cron_run(
            txs, self.search_count(domain), "payu_gpo_token_retry_date", retry
        )

    def _payu_gpo_on_tokenization_abandoned(self):
        """The card of this payment could not be saved: the buyer must enter
        it again. Extension point to tell someone (staff, the buyer)."""
        _logger.error(
            "PayU: gave up saving the card of %s; the buyer must enter it again.",
            self.reference,
        )

    def _payu_gpo_extract_token_values(self):
        """Token values of the card of this payment, or {}.

        The token PayU returned with the order is used as is. Otherwise the
        card is looked up among the buyer's stored ones.
        """
        if self.sudo().payu_gpo_card_token:
            return {
                "provider_ref": self.sudo().payu_gpo_card_token,
                "payment_details": (self.payu_gpo_card_mask or "")[-4:],
            }
        methods = self._payu_gpo_get_buyer_pay_methods()
        return self._payu_gpo_token_values_from_pay_methods(methods) if methods else {}

    def _payu_gpo_get_buyer_pay_methods(self):
        """The buyer's stored tokens (cardTokens, blikTokens...), or {}."""
        client = self.provider_id._payu_gpo_client()
        try:
            buyer_token = client.get_trusted_merchant_token(
                self.partner_email, self._payu_gpo_ext_customer_id()
            )
            return client.get_pay_methods(buyer_token)
        except PayuError as e:
            _logger.warning("PayU: could not list tokens for %s: %s", self.reference, e)
            return {}

    def _payu_gpo_token_values_from_pay_methods(self, methods):
        """The TOKC_ token of the card of this payment among the buyer's
        stored methods, or {}.

        The card is recognised by its masked number, and only when exactly one
        active card matches: PayU's "preferred" card may be another one of the
        buyer's cards.

        Extension point for other token types (e.g. BLIK PAYID).
        """
        mask = self.payu_gpo_card_mask
        cards = [
            card
            for card in methods.get("cardTokens", [])
            if card.get("status") == "ACTIVE"
            and card.get("value", "").startswith("TOKC_")
            and mask
            and card.get("cardNumberMasked") == mask
        ]
        if len(cards) != 1:
            return {}
        return {
            "provider_ref": cards[0]["value"],
            "payment_details": mask[-4:],
        }
