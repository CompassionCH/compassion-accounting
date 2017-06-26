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
#    Copyright (C) 2014-2017 Compassion CH (http://www.compassion.ch)
#    @author: Cyril Sester <csester@compassion.ch>, Emanuel Cino
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
    'name': 'Recurring contract',
    'summary': 'Contract for recurring invoicing',
    'version': '10.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Compassion CH',
    'website': 'http://www.compassion.ch',
    'category': 'Accounting',
    'depends': ['account_payment_partner', 'queue_job', 'account_cancel'],
    'external_dependencies': {},
    'data': [
        'views/contract_group_view.xml',
        'views/recurring_contract_view.xml',
        'views/res_partner_view.xml',
        'views/recurring_invoicer_view.xml',
        'views/recurring_invoicer_wizard_view.xml',
        'workflow/recurring_contract_workflow.xml',
        'data/recurring_contract_sequence.xml',
        'data/recurring_invoicer_sequence.xml',
        'data/contract_expire_cron.xml',
        'data/daily_invoicer_cron.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
}
