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
         ])

    openupgrade.update_module_moved_fields(
        cr, 'recurring.contract', [
            'activation_date'
        ],
        'contract_compassion', 'recurring_contract'
    )
    openupgrade.update_module_moved_fields(
        cr, 'utm.medium', [
            'type'
        ],
        'contract_compassion', 'recurring_contract'
    )

    openupgrade.delete_model_workflow(cr, 'recurring.contract', True)
