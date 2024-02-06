from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    analytic_tag_id = fields.Many2one('account.analytic.tag', string='Analytic Tag',
                                      readonly=False, help="analytic tag id to use "
                                      "when automatic move are created."
                                      )

    def set_values(self):
        super().set_values()
        self.env["ir.config_parameter"].sudo().set_param(
            "account_analytic_compassion.analytic_tag_id",
            str(self.analytic_tag_id.id),
        )

    @api.model
    def get_values(self):
        res = super().get_values()
        param_obj = self.env["ir.config_parameter"].sudo()
        res["analytic_tag_id"] = int(
            param_obj.get_param(
                "account_analytic_compassion.analytic_tag_id"
            )
        )
        return res
