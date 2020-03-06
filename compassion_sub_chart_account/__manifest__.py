# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
# pylint: disable=C8101
{
    'name': 'Comapssion subsidiary- Accounting',
    'version': '10.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'CompassionCH',
    'website': 'http://www.compassion.ch',
    'category': 'Localization',
    'depends': ['product', 'account'],
    'data': [
        'security/record_rules.xml',
        'data/l10n_compassion_sub_chart_data.xml',
    ],
}
