Create one provider per company in *Accounting > Configuration > Payment
Providers* and fill in the POS id, the OAuth `client_id` / `client_secret`
and the second key from the PayU merchant panel. State *Test* uses the
sandbox (`secure.snd.payu.com`).

PayU must enable on the POS:

- **automatic collection** (auto-receive) for every payment method: the
  module does not capture payments, and PayU cancels an uncaptured one
  (`WAITING_FOR_CONFIRMATION`) after a few days;
- **card tokens**: recurring payments (`recurring`) and/or cards on file
  (`cardOnFile`), and the `trusted_merchant` grant used to list the buyer's
  card tokens.

PayU must reach the notification URL. When Odoo's base URL is not public
(reverse proxy, development behind a tunnel), set the system parameter
`payment_payu_gpo.notify_base_url` to the public URL that forwards
`/payment/payu_gpo/webhook` to Odoo; the buyer still returns to the base URL.

Behind a reverse proxy, run Odoo with `proxy_mode = True`: the buyer's IP
address is sent to PayU with card payments (3-D Secure, fraud checks).

A neutralized copy of the database (`odoo-bin neutralize`) has its PayU keys
wiped, and a disabled provider never calls PayU.
