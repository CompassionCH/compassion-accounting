.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
    :alt: License: AGPL-3

Analytic attribution
====================

This module connects analytic defaults to analytic accounts in order to
apply a distribution for attributing analytic lines into other axis of
analysis.

The approach is different of module account_analyt_secondaxis as all move
lines are still related to only one analytic account, but later on, the user
can attribute the lines into other analytic accounts.

Usage
=====

To use this module, you need to:

* Create analytic attributions and link them to specific analytic accounts you
  want to attribute in other accounts.
* go to Accounting -> Configuration -> Analytic Accounting -> Launch
  attribution in order to attribute the lines for the given period. If an
  attribution was already made for the period, it recomputes everything.
* The attribution is automatically done when a period is closed.

Known issues / Roadmap
======================

* Maybe setup a CRON which will perform the attribution each month.
* Perform the attribution when closing a period.

Credits
=======

Contributors
------------

* Emanuel Cino <ecino@compassion.ch>

Maintainer
----------

This module is maintained by `Compassion Switzerland <https://www.compassion.ch>`.
