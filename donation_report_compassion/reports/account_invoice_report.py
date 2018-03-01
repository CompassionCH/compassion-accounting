# -*- coding: utf-8 -*-

from odoo import models, fields


class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"

    fiscal_month_number = fields.Integer()
    valid_month = fields.Boolean(
        help='Is the fiscal month already passed in current fiscal year?'
    )
    fiscal_year = fields.Char()

    def _select(self):
        """
        Add fiscal month in VIEW columns
        July is the first month and June is the twelve month
        """
        select_str = super(AccountInvoiceReport, self)._select()
        select_str += """,
            CASE WHEN EXTRACT(month FROM sub.date) > 6
            THEN EXTRACT(month FROM sub.date) - 6
            ELSE EXTRACT(month FROM sub.date) + 6
            END
            AS fiscal_month_number,

            CASE WHEN EXTRACT(month FROM now()) > 6
            THEN
                CASE WHEN EXTRACT(month FROM sub.date) > 6
                THEN EXTRACT(month FROM sub.date) - 6 < EXTRACT(
                    month FROM now()) - 6
                ELSE EXTRACT(month FROM sub.date) + 6 < EXTRACT(
                    month FROM now()) - 6
                END
            ELSE
                CASE WHEN EXTRACT(month FROM sub.date) > 6
                THEN EXTRACT(month FROM sub.date) - 6 < EXTRACT(
                    month FROM now()) + 6
                ELSE EXTRACT(month FROM sub.date) + 6 < EXTRACT(
                    month FROM now()) + 6
                END
            END
            AS valid_month,

            'FY ' ||
            CASE WHEN EXTRACT(month FROM sub.date) > 6
            THEN EXTRACT(year FROM sub.date)::varchar || '-' ||
                 (EXTRACT(year FROM sub.date)::int + 1)::varchar
            ELSE (EXTRACT(year FROM sub.date)::int - 1)::varchar || '-' ||
                 EXTRACT(year FROM sub.date)::varchar
            END
            AS fiscal_year
            """
        return select_str
