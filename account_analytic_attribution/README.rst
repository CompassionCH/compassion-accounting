.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
    :alt: License: AGPL-3

Analytic attribution
====================

This module is meant to be the successor of Odoo 8 Analytic Plans.
However, it works a bit differently. Instead of directly
dispatch analytic lines into several analytic accounts, you can setup rules
on how you want to perform the distribution, and distribution will be done
periodically (or can be triggered manually).

Configuration
=============
In order to use Analytic Distribution, you must first set analytic tags
on the analytic accounts for which you want to dispatch the analytic lines.
Those tags will be used to create the rules.

The module comes with a CRON `Perform Analytic Distribution` that you can
enable to launch the attribution automatically when you want. It will
perform the distribution for the last fiscal year (closed period). One good
idea is to setup the CRON to launch at the beginning of your fiscal year.

Usage
=====

To use this module, go to menu Accounting/Configuration/Analytic Accounting:

* Create analytic attributions: choose an analytic tag and setup the
  distribution applied for this tag. You can add conditions to filter analytic
  lines that will be distributed.
* The distribution is either performed with the CRON or you can launch it
  manually for the current fiscal year using the menu `Launch Distribution`

Known issues / Roadmap
======================

* None

Credits
=======

Contributors
------------

* Emanuel Cino <ecino@compassion.ch>

Maintainer
----------

This module is maintained by `Compassion Switzerland <https://www.compassion.ch>`.
