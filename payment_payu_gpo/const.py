##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################

PROVIDER_CODE = "payu_gpo"

# Currencies a PayU GPO point of sale can be opened in.
# See https://developers.payu.com/europe/docs/get-started/ (currencies section).
SUPPORTED_CURRENCIES = [
    "PLN",
    "EUR",
    "CZK",
    "HUF",
    "RON",
    "USD",
    "GBP",
    "CHF",
    "DKK",
    "NOK",
    "SEK",
]

# Payment methods activated with the provider. Recurrence is card-only for now;
# BLIK recurring (PAYID tokens, model "O") needs a contract annex - phase 2.
DEFAULT_PAYMENT_METHOD_CODES = {"card", "blik", "visa", "mastercard"}

# Payment methods paid through the Secure Form (direct flow) instead of the
# hosted page: PayU only stores a card for recurring charges from a form token.
CARD_PAYMENT_METHOD_CODES = {"card", "visa", "mastercard", "maestro"}

# Days during which the cron retries saving the card of a completed payment.
TOKENIZATION_RETRY_DAYS = 3
# Transactions per cron batch (committed one by one), and the minimal delay
# before the same transaction is tried again.
TOKENIZATION_RETRY_BATCH = 10
TOKENIZATION_RETRY_DELAY_MINUTES = 30

# Secure Form SDK, loaded by the browser from PayU.
SDK_PATH = "/javascript/sdk"

# PayU order status -> Odoo transaction state.
# See https://developers.payu.com/europe/docs/get-started/integration-overview/#order-statuses
STATUS_MAPPING = {
    "pending": ("NEW", "PENDING", "WAITING_FOR_CONFIRMATION"),
    "done": ("COMPLETED",),
    "canceled": ("CANCELED",),
}
