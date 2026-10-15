- Validate the notification payloads (order, refund) against production data.
- BLIK recurring (PAYID token, model "O", 2000 PLN cap) needs a contract
  annex with PayU; it is Poland-specific and belongs in a separate module.
- PayU does not retry declined merchant-initiated charges: the retry policy
  is left to the calling module.
- Odoo 19/20 port: `payu_client.py` has no Odoo import. The `_payu_gpo_*`
  helpers of `payment.transaction` map one-to-one onto the Odoo 19/20 hooks
  `_extract_reference`, `_apply_updates` and `_extract_token_values`. Odoo 20
  also forbids direct `write()` on transactions outside `payment_safe_write`
  / `_record()`.
