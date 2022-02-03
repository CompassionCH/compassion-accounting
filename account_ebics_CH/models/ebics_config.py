# Copyright 2020 Compassion.
# License LGPL-3 or later (http://www.gnu.org/licenses/lpgl).

from odoo import  models

class EbicsConfig(models.Model):
    _inherit = 'ebics.config'

    ebics_file_format_ids = fields.Many2many(
        comodel_name='ebics.file.format',
        column1='config_id', column2='format_id',
        string='EBICS File Formats',
    )
