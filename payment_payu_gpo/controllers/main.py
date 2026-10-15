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

from werkzeug.exceptions import Forbidden

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing

from ..const import PROVIDER_CODE
from ..payu_client import PayuError, verify_signature

_logger = logging.getLogger(__name__)


class PayuGpoController(http.Controller):
    _return_url = "/payment/payu_gpo/return"
    _webhook_url = "/payment/payu_gpo/webhook"
    _card_payment_url = "/payment/payu_gpo/card_payment"

    @http.route(_card_payment_url, type="json", auth="public")
    def payu_gpo_card_payment(self, reference, access_token, card_token, browser=None):
        """Pay a direct-flow transaction with the Secure Form token.

        :param dict browser: screen/timezone/language data collected by the
                             browser; HTTP headers and IP are added here

        :return: {"redirect_url": 3DS/CVV page to send the buyer to, or None}
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
        if tx.state != "draft":
            raise ValidationError(_("PayU: this payment was already processed."))
        if browser is not None:
            headers = request.httprequest.headers
            browser = {
                **browser,
                "acceptHeaders": headers.get("Accept", "*/*"),
                "userAgent": headers.get("User-Agent", ""),
                "requestIP": payment_utils.get_customer_ip_address(),
            }
        return {"redirect_url": tx._payu_gpo_pay_with_card_token(card_token, browser)}

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
        tx = request.env["payment.transaction"].sudo().browse(tx_id).exists()
        if tx and tx.provider_code == PROVIDER_CODE and tx.provider_reference:
            try:
                tx._payu_gpo_refresh_from_api()
            except (PayuError, ValidationError):
                _logger.exception("PayU: could not refresh %s on return", tx.reference)
        return request.redirect("/payment/status")

    @http.route(_webhook_url, type="http", methods=["POST"], auth="public", csrf=False)
    def payu_gpo_webhook(self):
        """Order and refund status notifications, signed with the POS second key."""
        raw_body = request.httprequest.get_data()
        data = json.loads(raw_body or b"{}")
        _logger.info("Notification received from PayU:\n%s", pprint.pformat(data))
        Transaction = request.env["payment.transaction"].sudo()
        try:
            reference = Transaction._payu_gpo_extract_reference(data)
            tx = Transaction.search(
                [("reference", "=", reference), ("provider_code", "=", PROVIDER_CODE)],
                limit=1,
            )
            if not tx:
                raise ValidationError(f"PayU: unknown reference {reference}")
            signature = request.httprequest.headers.get("OpenPayu-Signature")
            if not verify_signature(
                raw_body, signature, tx.provider_id.payu_gpo_second_key
            ):
                _logger.warning("PayU: invalid signature for %s", reference)
                raise Forbidden()
            tx._handle_notification_data(PROVIDER_CODE, data)
        except ValidationError:
            # Acknowledge anyway, otherwise PayU keeps retrying for days.
            _logger.exception("PayU: unable to handle the notification; acknowledging")
        return request.make_json_response("")
