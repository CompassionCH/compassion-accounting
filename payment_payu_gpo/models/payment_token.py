##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import fields, models

from .. import const


class PaymentToken(models.Model):
    _inherit = "payment.token"

    payu_gpo_recurring = fields.Boolean(
        string="PayU recurring card",
        readonly=True,
        help="Saved for scheduled recurring charges (recurring=STANDARD); other"
        " cards are charged as cards on file (cardOnFile=STANDARD_MERCHANT).",
    )

    def _get_available_tokens(
        self, providers_ids, partner_id, is_validation=False, **kwargs
    ):
        """Saved PayU cards are charged without the buyer only: paying with
        one on the site would be a customer-initiated payment, which needs
        the cardholder flags and 3DS handling this module does not have."""
        tokens = super()._get_available_tokens(
            providers_ids, partner_id, is_validation=is_validation, **kwargs
        )
        if is_validation:  # the buyer's saved cards, to manage them
            return tokens
        return tokens.filtered(lambda t: t.provider_code != const.PROVIDER_CODE)
