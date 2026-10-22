from unittest.mock import MagicMock, patch

from odoo.addons.payment.tests.common import PaymentCommon

from .. import payu_client
from ..payu_client import PayuClient

SECOND_KEY = "b6ca15b0d1020e8094d9b5f8d163db54"

INVALID_JSON = object()


def payu_response(status_code, body):
    """An HTTP answer of PayU; body INVALID_JSON is not JSON at all."""
    response = MagicMock(status_code=status_code)
    if body is INVALID_JSON:
        response.json.side_effect = ValueError("not JSON")
    else:
        response.json.return_value = body
    return response


class PayuGpoCommon(PaymentCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency = cls.env.ref("base.PLN")
        cls.currency.active = True
        # _prepare_provider copies an existing PayU provider into the test
        # company: one published on another company's website (e.g. the
        # Polish one) would carry that website along and be refused.
        providers = cls.env["payment.provider"].search([("code", "=", "payu_gpo")])
        if "website_id" in providers._fields:
            providers.website_id = False
        cls.provider = cls._prepare_provider(
            "payu_gpo",
            update_values={
                "payu_gpo_pos_id": "300746",
                "payu_gpo_client_id": "300746",
                "payu_gpo_client_secret": "2ee86a66e5d97e3fadc400c9f19b065d",
                "payu_gpo_second_key": SECOND_KEY,
            },
        )
        # Only this provider's payments for the crons, whatever the database
        # holds (e.g. a copy of production).
        (providers - cls.provider).state = "disabled"
        cls.payment_method_id = cls.env.ref("payment.payment_method_card").id
        cls.order_id = "WZHF5FFDRJ140731GUEST000P01"

    def _order_notification(self, status, reference=None):
        return {
            "order": {
                "orderId": self.order_id,
                "extOrderId": reference or self.reference,
                "status": status,
                "totalAmount": "111111",
                "currencyCode": "PLN",
            }
        }

    def _payu_answers(self, *answers):
        """Patch the provider's client: the real PayuClient, whose transport
        gives these (HTTP status, body) answers in turn."""
        session = MagicMock()
        session.post.return_value = payu_response(
            200, {"access_token": "T", "expires_in": 3600}
        )
        session.request.side_effect = [payu_response(*answer) for answer in answers]
        payu_client._TOKEN_CACHE.clear()
        self.addCleanup(payu_client._TOKEN_CACHE.clear)
        client = PayuClient("300746", "300746", "s", sandbox=True, session=session)
        return patch.object(
            type(self.env["payment.provider"]), "_payu_gpo_client", return_value=client
        )
