- Validate the notification payloads (order, refund) against production data.
- Not supported yet:
  - saving a card without paying (card validation): PayU needs a
    zero-amount order, enabled on a POS on request;
  - paying with a saved card while the buyer is on the site
    (`cardOnFile: STANDARD_CARDHOLDER` and the 3DS / CVV redirects): saved
    PayU cards are only charged without the buyer;
  - the CVV that PayU may ask for a card (`WARNING_CONTINUE_CVV`, through
    the Secure Form `sendCvv`): the payment is refused with a clear message;
  - manual capture (`WAITING_FOR_CONFIRMATION`, `authorized` state);
  - refunds made in the PayU panel, and reading the status of a refund whose
    notification was lost.
- BLIK recurring (PAYID token, model "O", 2000 PLN cap) needs a contract
  annex with PayU; it is Poland-specific and belongs in a separate module.
- PayU does not retry declined merchant-initiated charges: the retry policy
  is left to the calling module.
- Odoo 19/20 port: `payu_client.py` has no Odoo import. The `_payu_gpo_*`
  helpers of `payment.transaction` map one-to-one onto the Odoo 19/20 hooks
  `_extract_reference`, `_apply_updates` and `_extract_token_values`. Odoo 20
  also forbids direct `write()` on transactions outside `payment_safe_write`
  / `_record()`.
