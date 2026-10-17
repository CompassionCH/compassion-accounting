Payment provider for **PayU GPO** (Europe, `secure.payu.com`, REST API v2.1).
Not to be confused with PayU India (`payu.in`).

- Hosted payment page (redirect) for BLIK and other non-card methods.
- A "Name on card" field next to the Secure Form (which asks none): sent to
  PayU as 3-D Secure cardholder data and as the buyer's name, so the payer's
  name comes back in PayU's notification.
- Card payments through the PayU Secure Form, with card tokenization: the
  first payment is sent with `recurring: FIRST`; once `COMPLETED`, the
  multi-use `TOKC_` token is stored as a `payment.token`.
- Merchant-initiated charges: `_send_payment_request()` charges the token
  with `recurring: STANDARD`, so any off-session charge (cron, subscription)
  works with the standard payment API.
- When the card of a completed payment cannot be read from PayU (e.g. after
  3DS), an hourly cron retries saving it for three days.
- When PayU's notification of a payment is lost (Odoo down or not reachable),
  a cron reads the status of the payments still pending every 15 minutes, for
  two days.
- Signed notifications (`OpenPayu-Signature`, POS second key) for orders and
  refunds.
- Partial and full refunds.
