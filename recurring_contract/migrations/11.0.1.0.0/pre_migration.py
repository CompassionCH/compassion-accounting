# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    @author: Nathan Fluckiger  <nathan.fluckiger@hotmail.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from openupgradelib import openupgrade


def migrate(cr, version):
    if not version:
        return

    openupgrade.rename_xmlids(
        cr,
        [('contact_compassion.utm_medium_post',
          'recurring_contract.utm_medium_post'),
         ('contact_compassion.utm_medium_payment',
          'recurring_contract.utm_medium_payment'),
         ('contact_compassion.utm_medium_instagram',
          'recurring_contract.utm_medium_instagram'),
         ('contact_compassion.utm_medium_mass_mailing',
          'recurring_contract.utm_medium_mass_mailing'),
         ('contact_compassion.utm_campaign_sub',
          'recurring_contract.utm_campaign_sub'),
         ('contact_compassion.utm_source_sub',
          'recurring_contract.utm_source_sub'),
         ('contact_compassion.product_category_fund',
          'recurring_contract.product_category_fund'),
         ('contact_compassion.utm_medium_post',
          'recurring_contract.utm_medium_post'),
         ('contact_compassion.utm_medium_post',
          'recurring_contract.utm_medium_post'),
         ('contact_compassion.utm_medium_post',
          'recurring_contract.utm_medium_post'),
         ('contact_compassion.utm_medium_post',
          'recurring_contract.utm_medium_post')
         ])
