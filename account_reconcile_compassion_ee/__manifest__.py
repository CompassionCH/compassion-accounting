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
#    Copyright (C) 2025 Compassion CH (http://www.compassion.ch)
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

# pylint: disable=C8101
{
    "name": "Enterprise Bank Statement Reconcile for Compassion",
    "version": "17.0.1.0.4",
    "author": "Compassion CH",
    "license": "AGPL-3",
    "category": "Finance",
    "website": "https://github.com/CompassionCH/compassion-accounting",
    "depends": [
        "account_accountant",
        "analytic",
        "gift_compassion",
        "thankyou_letters",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/account_reconcile_model_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_reconcile_compassion_ee/static/src/components/**/*",
        ],
    },
    "excludes": ["account_reconcile_oca", "account_reconcile_model_oca"],
    "auto_install": False,
    "installable": True,
}
