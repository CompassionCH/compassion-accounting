Payment provider for **PayU GPO** (Europe, `secure.payu.com`, REST API v2.1).
Not to be confused with PayU India (`payu.in`).

- Hosted payment page (redirect) for BLIK and other non-card methods.
- Card payments through the PayU Secure Form, with card tokenization: the
  first payment is sent with `recurring: FIRST`; once `COMPLETED`, the
  multi-use `TOKC_` token is stored as a `payment.token`.
- Merchant-initiated charges: `_send_payment_request()` charges the token
  with `recurring: STANDARD`, so any off-session charge (cron, subscription)
  works with the standard payment API.
- Signed notifications (`OpenPayu-Signature`, POS second key) for orders and
  refunds.
- Partial and full refunds.
