# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    @author: Quentin Gigon <gigon.quentin@gmail.com>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
# pylint: disable=C8101
{
    'name': 'Account move open bills to next fiscal year',
    'version': '12.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Compassion CH',
    'website': 'http://www.compassion.ch',
    'category': 'Accounting',
    'depends': [
        'account',                      # source/addons/account
        'account_lock_date_update'      # oca_addons/account-financial-tools
    ],
    'external_dependencies': {},
    'data': ['views/res_config_bills_view.xml'],
    'demo': [],
    'installable': True,
}
