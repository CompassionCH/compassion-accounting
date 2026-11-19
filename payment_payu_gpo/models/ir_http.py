##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _get_translation_frontend_modules_name(cls):
        """The card form's messages (payment_form.esm.js) in the website's
        language."""
        return super()._get_translation_frontend_modules_name() + ["payment_payu_gpo"]
