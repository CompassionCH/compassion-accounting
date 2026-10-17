from odoo.addons.payment.tests.common import PaymentCommon

SECOND_KEY = "b6ca15b0d1020e8094d9b5f8d163db54"


class PayuGpoCommon(PaymentCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency = cls.env.ref("base.PLN")
        cls.currency.active = True
        # _prepare_provider copies an existing PayU provider into the test
        # company: one published on another company's website (e.g. the
        # Polish one) would carry that website along and be refused.
        cls.env["payment.provider"].search(
            [("code", "=", "payu_gpo")]
        ).website_id = False
        cls.provider = cls._prepare_provider(
            "payu_gpo",
            update_values={
                "payu_gpo_pos_id": "300746",
                "payu_gpo_client_id": "300746",
                "payu_gpo_client_secret": "2ee86a66e5d97e3fadc400c9f19b065d",
                "payu_gpo_second_key": SECOND_KEY,
            },
        )
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
