# -*- coding: utf-8 -*-
# Copyright 2018 Compassion Suisse
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
# pylint: disable=C8101
{
    'name': 'MIS Builder event & sponsorship info',
    'summary': """
        Events, acquisition for MIS Builder""",
    'version': '10.0.3.0.0',
    'license': 'AGPL-3',
    'author': 'compassion suisse',
    'website': 'https://github.com/OCA/mis-builder',
    'depends': [
        'mis_builder',
        'crm_compassion',
        'account',
    ],
    'data': [
        'security/mis_spn_event_info.xml',
        'views/mis_spn_event_info.xml',
    ],
    'installable': False,
    'maintainers': ['davidwul'],
}
