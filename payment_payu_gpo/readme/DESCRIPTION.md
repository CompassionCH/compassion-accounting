Payment provider for **PayU GPO** (Europe, `secure.payu.com`, REST API v2.1).
Not to be confused with PayU India (`payu.in`).

- Hosted payment page (redirect) for BLIK and other non-card methods.
- Card payments through the PayU Secure Form, with a "Name on card" field
  next to it (the Secure Form asks none): sent to PayU as 3-D Secure
  cardholder data and as the buyer's name, so the payer's name comes back in
  PayU's notification.
- Card tokenization: a card saved on payment is a card on file
  (`cardOnFile: FIRST`), or a card for scheduled recurring charges
  (`recurring: FIRST`) when `_payu_gpo_card_is_recurring()` says so. The
  multi-use `TOKC_` token PayU returns with the order is saved as a
  `payment.token` once the order is `COMPLETED`.
- Merchant-initiated charges: `_send_payment_request()` charges the token
  without the buyer (`recurring: STANDARD`, or `cardOnFile:
  STANDARD_MERCHANT`), so any off-session charge (cron, subscription) works
  with the standard payment API. A charge the bank refuses (PayU cancels the
  order, or asks for the cardholder) is set to error, not cancelled: nobody
  gave it up.
- A request PayU did not answer (timeout, 5xx) leaves the payment pending:
  the order may exist, and its notification settles it. A payment or refund
  PayU never confirms (no PayU id, no notification) is set to error after
  four days, once PayU has stopped retrying its notifications (72 hours),
  and flagged `payu_gpo_unconfirmed`: its outcome is unknown, which is not a
  refusal. A final answer from PayU that still comes clears the flag: the
  payment is then done, or stays in error as a certain refusal.
- When the card of a completed payment cannot be read from PayU, an hourly
  cron retries saving it for three days.
- When PayU's notification of a payment is lost (Odoo down or not reachable),
  a cron reads the status of the payments still pending every 15 minutes, for
  two days, and the payment status page reads it while the buyer waits.
- Signed notifications (`OpenPayu-Signature`, POS second key) for orders and
  refunds, checked against the payment (PayU order, amount, currency).
- Partial and full refunds.
