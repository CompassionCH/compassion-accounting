# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Coninckx David <david@coninckx.com>
#
#    The licence is in the file __openerp__.py
#
##############################################################################
import sys


def migrate(cr, version):
    reload(sys)
    sys.setdefaultencoding('UTF8')

    if not version:
        return
    delay_dict = {'annual': 12, 'biannual': 6, 'fourmonthly': 4,
                  'quarterly': 3, 'bimonthly': 2, 'monthly': 1}
    cr.execute(
        '''
        SELECT id, advance_billing FROM recurring_contract_group
        '''
    )

    contract_groups = cr.fetchall()

    for contract_group in contract_groups:
        delay = delay_dict[contract_group[1]] or 1
        cr.execute(
            '''
            UPDATE recurring_contract_group
            SET advance_billing_months = {0}
            WHERE id = {1}
            '''.format(delay, contract_group[0])

        )
