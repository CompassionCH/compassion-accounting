Create one provider per company in *Accounting > Configuration > Payment
Providers* and fill in the POS id, the OAuth `client_id` / `client_secret`
and the second key from the PayU merchant panel. State *Test* uses the
sandbox (`secure.snd.payu.com`).

PayU must enable **recurring payments** on the POS (cards), and the
`trusted_merchant` grant used to list the buyer's card tokens.
