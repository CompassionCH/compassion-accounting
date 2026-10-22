##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import json
import logging
import pprint

from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing

from ..const import PROVIDER_CODE
from ..payu_client import verify_signature

_logger = logging.getLogger(__name__)

# threeDsAuthentication.browser keys the payment form sends.
BROWSER_KEYS = {
    "screenWidth",
    "screenHeight",
    "colorDepth",
    "javaEnabled",
    "timezoneOffset",
    "language",
}


def refresh_if_due(tx):
    """Read a pending PayU payment from PayU, never failing the caller: the
    status page stops polling on any error, and would then never end."""
    if not tx or tx.provider_code != PROVIDER_CODE:
        return
    try:
        with request.env.cr.savepoint():
            tx._payu_gpo_refresh_if_due()
    except Exception:
        _logger.exception("PayU: could not read the status of %s", tx.reference)


class PayuGpoPostProcessing(PaymentPostProcessing):
    @http.route()
    def poll_status(self, **kwargs):
        """Ask PayU about a payment still pending before reporting its state:
        without the notification the status page would never end."""
        refresh_if_due(self._get_monitored_transaction())
        return super().poll_status(**kwargs)


class PayuGpoController(http.Controller):
    _return_url = "/payment/payu_gpo/return"
    _webhook_url = "/payment/payu_gpo/webhook"
    _card_payment_url = "/payment/payu_gpo/card_payment"
    _cancel_url = "/payment/payu_gpo/cancel"

    @staticmethod
    def _payu_gpo_lock_transaction(reference, access_token):
        """The PayU transaction of reference, checked against the access token
        of its processing values and locked until the end of the request.

        The card and cancel requests of a payment then never overlap, and a
        notification of the payment waits: on a conflict Odoo retries the
        notification, never these requests, which a replay would find
        already processed.
        """
        if not payment_utils.check_access_token(access_token, reference):
            raise ValidationError(_("PayU: received tampered payment request data."))
        tx = (
            request.env["payment.transaction"]
            .sudo()
            .search(
                [("reference", "=", reference), ("provider_code", "=", PROVIDER_CODE)],
                limit=1,
            )
        )
        if not tx:
            raise ValidationError(_("PayU: unknown payment."))
        request.env.cr.execute(
            "SELECT 1 FROM payment_transaction WHERE id = %s FOR NO KEY UPDATE",
            [tx.id],
        )
        return tx

    @http.route(_card_payment_url, type="json", auth="public")
    def payu_gpo_card_payment(
        self,
        reference,
        access_token,
        card_token,
        browser=None,
        cardholder_name=None,
        card_mask=None,
    ):
        """Pay a direct-flow transaction with the Secure Form token.

        :param str card_token: the single-use TOK_ token of the Secure Form
        :param dict browser: screen/timezone/language data collected by the
                             browser; HTTP headers and IP are added here
        :param str cardholder_name: name on the card, typed next to the form
        :param str card_mask: masked card number returned by the Secure Form

        :return: {"redirect_url": 3DS page to send the buyer to, or None}
        """
        tx = self._payu_gpo_lock_transaction(reference, access_token)
        if not isinstance(card_token, str) or not card_token.startswith("TOK_"):
            raise ValidationError(_("PayU: invalid card token."))
        if tx.state != "draft":
            if tx.provider_reference:
                # Already sent to PayU (e.g. a replayed request): the status
                # page tells the outcome.
                return {"redirect_url": None}
            raise ValidationError(_("PayU: this payment was already processed."))
        if isinstance(browser, dict):
            headers = request.httprequest.headers
            browser = {
                **{k: v for k, v in browser.items() if k in BROWSER_KEYS},
                "acceptHeaders": headers.get("Accept", "*/*"),
                "userAgent": headers.get("User-Agent", ""),
                "requestIP": payment_utils.get_customer_ip_address(),
            }
        else:
            browser = None
        return {
            "redirect_url": tx._payu_gpo_pay_with_card_token(
                card_token,
                browser,
                cardholder_name if isinstance(cardholder_name, str) else None,
                card_mask if isinstance(card_mask, str) else None,
            )
        }

    @http.route(_cancel_url, type="json", auth="public")
    def payu_gpo_cancel(self, reference, access_token):
        """Cancel a card payment whose card the Secure Form refused (a typo,
        an expired card), before the buyer tries again: nothing reached PayU,
        and a draft left behind blocks what it pays until it is cleaned up.

        Only a draft is cancelled: the card route moves the payments it sends
        to PayU to pending or error, under the same lock.
        """
        tx = self._payu_gpo_lock_transaction(reference, access_token)
        if tx.state == "draft":
            tx._set_canceled()

    @http.route(_return_url, type="http", methods=["GET"], auth="public")
    def payu_gpo_return(self, **data):
        """Buyer comes back from the PayU page (continueUrl).

        The query string says nothing about the payment: PayU sends
        statusCode=SUCCESS even when the buyer abandons. The real outcome is
        read from the API so the status page is right even before the
        notification arrives.
        """
        _logger.info("Return from PayU with data:\n%s", pprint.pformat(data))
        tx_id = request.session.get(PaymentPostProcessing.MONITORED_TX_ID_KEY)
        refresh_if_due(request.env["payment.transaction"].sudo().browse(tx_id).exists())
        return request.redirect("/payment/status")

    @http.route(_webhook_url, type="http", methods=["POST"], auth="public", csrf=False)
    def payu_gpo_webhook(self):
        """Order and refund status notifications, signed with the POS second key.

        Nothing of an unsigned request is trusted or logged in full: only its
        reference, to tell a real notification from noise.
        """
        signature = request.httprequest.headers.get("OpenPayu-Signature")
        if not signature:
            raise BadRequest()
        raw_body = request.httprequest.get_data()
        try:
            data = json.loads(raw_body or b"{}")
        except ValueError as e:
            raise BadRequest() from e
        if not isinstance(data, dict):
            raise BadRequest()
        Transaction = request.env["payment.transaction"].sudo()
        try:
            reference = Transaction._payu_gpo_extract_reference(data)
        except ValidationError:
            # Unusable, now and later: acknowledge, or PayU retries for days.
            _logger.warning("PayU: notification without reference; acknowledging")
            return request.make_json_response("")
        _logger.info("Notification received from PayU for %s", reference)
        tx = Transaction.search(
            [("reference", "=", reference), ("provider_code", "=", PROVIDER_CODE)],
            limit=1,
        )
        if not tx:
            # Possibly not committed yet (a refund notification may come before
            # the request that sent the refund ends): PayU will send it again.
            _logger.warning("PayU: unknown reference %s; PayU will retry", reference)
            raise NotFound()
        if not verify_signature(
            raw_body, signature, tx.provider_id.payu_gpo_second_key
        ):
            _logger.warning("PayU: invalid signature for %s", reference)
            raise Forbidden()
        _logger.debug("Notification from PayU:\n%s", pprint.pformat(data))
        try:
            tx._handle_notification_data(PROVIDER_CODE, data)
        except ValidationError:
            # Acknowledge anyway, otherwise PayU keeps retrying for days.
            _logger.exception("PayU: unable to handle the notification; acknowledging")
        return request.make_json_response("")
