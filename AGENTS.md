# Compassion Accounting · Odoo 18

These addons provide recurring contracts and invoicing, bank reconciliation and
statement import, payment-order helpers and PayU. Swiss and Nordic country addons depend
on them. PayU serves the Polish office, which the Swiss deployment hosts.

## Dependencies and translations

Declare the addons you use in the manifest's `depends`. Odoo refuses a dependency cycle
between addons: check the whole chain before adding a dependency on another repository's
addon. Every addon in that chain must also be available wherever this addon is
installed. Addons here can depend on `compassion-modules` and `compassion-website`,
never on a country repository; an addon that `compassion-modules` depends on, such as
`recurring_contract`, never on `compassion-website` either. Put new country-specific
behavior in a country extension. `account_ebics_payment_return` needs `account_ebics`,
which only the Swiss deployment has. The `_ee` addons need Odoo Enterprise, which only
the Nordic deployment has. Swiss sponsorship uses `account_reconcile_compassion_ce`,
whose `account_reconcile_model.py` and `account_reconcile_model_partner_matching.py` are
copied in `account_reconcile_compassion_ee`: apply a fix to either file in both addons.

If the module has catalogs, update its existing locales. For its first catalogs,
identify installing countries from country-addon dependencies or deployment
configuration. Ask the maintainer if coverage is unclear. Switzerland uses `fr_CH`,
`de_DE`, `it_IT`. The Nordic countries use `sv_SE`, `nb_NO`, `da_DK`, `fi_FI`. The
Polish office, which the Swiss deployment hosts, uses `pl_PL`: add it when the module
shows text to the Polish office's sponsors. Keep the PayU provider's existing `pl.po`.

## Where to find the rules

When a task changes code here, open the shared rule subjects it needs. If the toolkit
plugins are available, use their skills `code-rules:rules` and `odoo-rules:rules`;
otherwise fetch the published rules into a temporary folder:
`(d="$(mktemp -d)" && git clone -q --depth 1 --branch main https://github.com/CompassionCH/compassion-agent-toolkit.git "$d" && echo "$d")`.
There, each index is `plugins/<plugin>/skills/rules/SKILL.md`. If the sandbox blocks the
network, ask the user to run the command, or read the indexes online:
[code-rules](https://github.com/CompassionCH/compassion-agent-toolkit/blob/main/plugins/code-rules/skills/rules/SKILL.md)
[odoo-rules](https://github.com/CompassionCH/compassion-agent-toolkit/blob/main/plugins/odoo-rules/skills/rules/SKILL.md)

A payment or refund in Odoo's `error` state may have gone through at PayU. The portal
bridge `my_compassion_payment_payu_gpo` uses `_my2_refusal_is_certain` to block a second
charge while [`payu_gpo_unconfirmed`](payment_payu_gpo/models/payment_transaction.py) is
set. Block a refund retry if the previous refund transaction has this flag. A matching
final response clears it even if it arrives late.

## Before opening a PR

Run `pre-commit run` on staged files, or `pre-commit install` to enable the hooks on
commit. CI covers static checks only. It runs
`SKIP=oca-gen-addon-readme pre-commit run --all-files --show-diff-on-failure --color=always`
and checks for untracked generated files. The hooks exclude
`account_offbalance_sponsorship`: run `ruff check` and `ruff format` yourself on the
Python files you change there. Run the affected Odoo tests separately.

Then run the rules review in `review.md`, linked from the code-rules index. Use the
`code-rules:rules-reviewer` subagent when the plugin is available; otherwise give a
fresh read-only session the published reviewer prompt,
`plugins/code-rules/agents/rules-reviewer.md` in that folder
([online](https://github.com/CompassionCH/compassion-agent-toolkit/blob/main/plugins/code-rules/agents/rules-reviewer.md)).
Only if neither is possible, say in the PR description that no rules review ran. Record
findings, coverage gaps and their disposition there.
