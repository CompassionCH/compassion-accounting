# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################
from openerp.osv import orm


class account_period_close(orm.TransientModel):
    """ Launch analytic attribution when period is closed. """
    _inherit = "account.period.close"

    def data_save(self, cr, uid, ids, context=None):
        analytic_attribution_obj = self.pool.get(
            'account.analytic.attribution.wizard')
        analytic_attribution_id = analytic_attribution_obj.create(
            cr, uid, dict(), context)
        res = analytic_attribution_obj.perform_attribution(
            cr, uid, analytic_attribution_id, context)
        super(account_period_close, self).data_save(cr, uid, ids, context)
        return res


class account_fiscalyear_close(orm.TransientModel):
    """ Launch analytic attribution when fiscalyear is closed. """
    _inherit = "account.fiscalyear.close"

    def data_save(self, cr, uid, ids, context=None):
        data = self.browse(cr, uid, ids, context=context)
        fy_id = data[0].fy_id.id
        analytic_attribution_obj = self.pool.get(
            'account.analytic.attribution.wizard')
        analytic_attribution_id = analytic_attribution_obj.create(
            cr, uid, {
                'fiscalyear_id': fy_id}, context)
        res = analytic_attribution_obj.perform_attribution(
            cr, uid, analytic_attribution_id, context)
        super(account_fiscalyear_close, self).data_save(cr, uid, ids, context)
        return res


class account_fiscalyear_state_close(orm.TransientModel):
    """ Launch analytic attribution when fiscalyear is closed. """
    _inherit = "account.fiscalyear.close.state"

    def data_save(self, cr, uid, ids, context=None):
        data = self.browse(cr, uid, ids, context=context)
        fy_id = data[0].fy_id.id
        analytic_attribution_obj = self.pool.get(
            'account.analytic.attribution.wizard')
        analytic_attribution_id = analytic_attribution_obj.create(
            cr, uid, {
                'fiscalyear_id': fy_id}, context)
        res = analytic_attribution_obj.perform_attribution(
            cr, uid, analytic_attribution_id, context)
        super(account_fiscalyear_state_close, self).data_save(cr, uid, ids,
                                                              context)
        return res
