# -*- encoding: utf-8 -*-
##############################################################################
#
#       ______ Releasing children from poverty      _
#      / ____/___  ____ ___  ____  ____ ___________(_)___  ____
#     / /   / __ \/ __ `__ \/ __ \/ __ `/ ___/ ___/ / __ \/ __ \
#    / /___/ /_/ / / / / / / /_/ / /_/ (__  |__  ) / /_/ / / / /
#    \____/\____/_/ /_/ /_/ .___/\__,_/____/____/_/\____/_/ /_/
#                        /_/
#                            in Jesus' name
#
#    Copyright (C) 2015 Compassion CH (http://www.compassion.ch)
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
{
    'name': 'Analytic attribution',
    'summary': 'Set rules to dispatch analytic lines into analytic accounts',
    'version': '0.1',
    'license': 'AGPL-3',
    'author': 'Compassion CH',
    'website': 'http://www.compassion.ch',
    'category': 'Accounting',
    'depends': ['account_analytic_plans'],
    'external_dependencies': {},
    'data': [
        'data/install.xml',
        'view/account_analytic_default_view.xml',
        'view/analytic_attribution_view.xml',
        'view/account_view.xml',
    ],
    'demo': [],
    'description': """
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
    """,
    'active': False,
    'installable': True,
}
