# Copyright 2020 Compassion.
# License LGPL-3 or later (http://www.gnu.org/licenses/lpgl).

from odoo import fields, models


class EbicsFileFormat(models.Model):
    _inherit = "ebics.file.format"

    display_name = fields.Char(compute="_compute_display_name")

    def _supported_download_order_types(self):
        res = super()._supported_download_order_types()
        res.append("ZZT")
        res.append("ZZQ")
        return res

    def _compute_display_name(self):
        for record in self:
            record.display_name = record.name + " (" + record.order_type + ")"

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, record.display_name))
        return result
