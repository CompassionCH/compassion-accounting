##############################################################################
#
#    Copyright (C) 2014-2023 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models
from odoo.exceptions import UserError


class AccountPaymentLine(models.Model):
    _name = "account.payment.line"
    _inherit = "account.payment.line"

    def unlink(self):
        for line in self:
            if line.order_id.state not in [
                "draft",
                "open",
            ] and not self.env.context.get("force_pay_line_del", False):
                raise UserError(
                    f"You can't delete the line payment line related to the "
                    f"move line {line.move_line_id} "
                    f"on the payment order {line.order_id.name}"
                )
        super().unlink()
