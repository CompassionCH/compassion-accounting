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
#    Copyright (C) 2014-today Compassion CH (http://www.compassion.ch)
#    @author: David Wulliamoz <dwulliamoz@compassion.ch>
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
    "name": "account_offbalance_sponsorship",
    "summary": """
        Off-Balance accounting for sponsorships.
""",
    "author": "Compassion Switzerland, David Wulliamoz",
    "website": "https://github.com/CompassionCH/test-repo",
    "category": "sponsorship and donation",
    "license": "AGPL-3",
    "version": "14.0.1.0.0",
    # any module necessary for this one to work correctly
    "depends": [
        "base",
        "sponsorship_compassion",
        #'account_reconcile_compassion',
    ],
    # always loaded
    "data": [
        # 'security/ir.model.access.csv',
        "views/res_config_view.xml",
    ],
}
