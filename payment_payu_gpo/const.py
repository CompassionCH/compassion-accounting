##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import re

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

# Payment methods activated with the provider. Recurrence is card-only: BLIK
# recurring (PAYID tokens, model "O") needs a contract annex with PayU.
DEFAULT_PAYMENT_METHOD_CODES = {"card", "blik", "visa", "mastercard"}

# Payment methods paid through the Secure Form (direct flow) instead of the
# hosted page: PayU only stores a card for recurring charges from a form token.
CARD_PAYMENT_METHOD_CODES = {"card", "visa", "mastercard", "maestro"}

# Tokens the Secure Form returns: TOK_ for a card to save (MULTI), TOKD_ for a
# one-off payment (SINGLE). The card route takes nothing else, never a saved
# card's TOKC_ token, and only TOK_ when the card is to be saved.
MULTI_USE_TOKEN_PREFIX = "TOK_"
SECURE_FORM_TOKEN_PREFIXES = (MULTI_USE_TOKEN_PREFIX, "TOKD_")

# What a PayU order or refund id looks like (e.g. WZHF5FFDRJ140731GUEST000P01,
# 5001592615): only such a value is kept as a provider reference.
PAYU_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")

# Days during which the cron retries saving the card of a completed payment.
TOKENIZATION_RETRY_DAYS = 3
# Transactions per cron batch (committed one by one), and the minimal delay
# before the same transaction is tried again.
TOKENIZATION_RETRY_BATCH = 10
TOKENIZATION_RETRY_DELAY_MINUTES = 30

# Pending payments read again from PayU when their notification did not come
# (lost, or Odoo not reachable): after this delay, during these days, by
# batches, each one at most once per delay.
SYNC_PENDING_DELAY_MINUTES = 10
SYNC_PENDING_DAYS = 2
SYNC_PENDING_BATCH = 20
# Days after which a payment PayU never confirmed is set to error: longer than
# PayU's last notification retry (72 hours), so that no notification can still
# come. Its outcome stays unknown (payment.transaction.payu_gpo_unconfirmed).
UNCONFIRMED_FAIL_DAYS = 4
# The payment status page asks PayU itself, at most this often per payment,
# while the payment is pending (the notification may be late or lost).
SYNC_POLL_SECONDS = 10
# A cron batch stops after this time, well before Odoo's limit_time_real kills
# it: what is left goes to the next batch.
CRON_TIME_BUDGET_SECONDS = 60

# Secure Form SDK, loaded by the browser from PayU.
SDK_PATH = "/javascript/sdk"

# PayU order status -> Odoo transaction state.
# See https://developers.payu.com/europe/docs/get-started/integration-overview/#order-statuses
# WAITING_FOR_CONFIRMATION (authorized, not captured) only happens when
# automatic collection is off on the POS: it stays pending, with a warning.
STATUS_MAPPING = {
    "pending": ("NEW", "PENDING", "WAITING_FOR_CONFIRMATION"),
    "done": ("COMPLETED",),
    "canceled": ("CANCELED",),
}
# Any other order status, or refund status, concludes nothing: the payment is
# left as it is.
ORDER_STATUSES = tuple(status for group in STATUS_MAPPING.values() for status in group)
REFUND_STATUSES = ("PENDING", "CANCELED", "FINALIZED")
