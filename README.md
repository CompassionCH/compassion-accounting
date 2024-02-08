
<!-- /!\ Non OCA Context : Set here the badge of your runbot / runboat instance. -->
[![Pre-commit Status](https://github.com/CompassionCH/compassion-accounting/actions/workflows/pre-commit.yml/badge.svg?branch=14.0)](https://github.com/CompassionCH/compassion-accounting/actions/workflows/pre-commit.yml?query=branch%3A14.0)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=CompassionCH_compassion-accounting&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=CompassionCH_compassion-accounting)
<!-- /!\ Non OCA Context : Set here the badge of your translation instance. -->

<!-- /!\ do not modify above this line -->

# Compassion Accounting

All accounting extensions needed for supporting Compassion's mission, in particular with the child sponsosrhip program.

<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)

Available addons
----------------
addon | version | maintainers | summary
--- | --- | --- | ---
[account_analytic_attribution](account_analytic_attribution/) | 14.0.1.0.0 |  | Set rules to dispatch analytic lines into analytic accounts
[account_analytic_compassion](account_analytic_compassion/) | 14.0.1.0.0 |  | Compassion Analytic Accounts
[account_ebics_CH](account_ebics_CH/) | 14.0.1.0.0 |  | add specific EBICS order type and file format for Switzerland
[account_ebics_payment_return](account_ebics_payment_return/) | 14.0.1.0.0 |  | Download Payment Order return via EBICS
[account_invoice_split_invoice](account_invoice_split_invoice/) | 14.0.1.0.1 |  | Split invoices into two separate invoices
[account_move_periodic_accounting_transfer](account_move_periodic_accounting_transfer/) | 14.0.1.0.0 |  | Move from an ending accounting period to an open one
[account_payment_line_free](account_payment_line_free/) | 14.0.1.0.1 |  | Account payment line free
[account_statement_completion](account_statement_completion/) | 14.0.1.0.1 |  | Account Statement Completion Rules
[compassion_sub_chart_account](compassion_sub_chart_account/) | 14.0.1.0.0 |  | Comapssion subsidiary- Accounting
[donation_report_compassion](donation_report_compassion/) | 14.0.1.0.0 |  | Compassion Donation Report
[invoice_restrictions](invoice_restrictions/) | 14.0.1.0.5 |  | Contract for recurring invoicing
[recurring_contract](recurring_contract/) | 14.0.1.0.5 |  | Contract for recurring invoicing

[//]: # (end addons)

<!-- prettier-ignore-end -->

## Licenses

This repository is licensed under [AGPL-3.0](LICENSE).

However, each module can have a totally different license, as long as they adhere to Compassion Switzerland
policy. Consult each module's `__manifest__.py` file, which contains a `license` key
that explains its license.

----
<!-- /!\ Non OCA Context : Set here the full description of your organization. -->
