.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
    :alt: License: AGPL-3

Account Statement Additions for Compassion CH
=============================================

- Add three completion methods :
    1. Completion method based on the BVR reference of the contract
       or the invoice.
    2. Completion method based on the reference of the partner
    3. Completion method for Raiffaisen statements (supplier invoices) based
       only on the amount.

- The first rule is applied. If no contract or invoice is found with same
  BVR reference, then second rule is applied, and an invoice is generated
  on-the-fly for gifts or funds donations.
- The third rule is useful only for supplier invoices.

- Adds ability to generate invoices from the bank statement

- Adds field analytic account to move_line view

Credits
=======

Contributors
------------

* Emanuel Cino <ecino@compassion.ch>

Maintainer
----------

This module is maintained by `Compassion Switzerland <https://www.compassion.ch>`.