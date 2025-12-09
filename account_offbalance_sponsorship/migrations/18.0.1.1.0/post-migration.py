import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


# Associate off-balance lines to their on-balance counterparts
def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    on_balance_lines = env["account.move.line"].search(
        [
            ("is_off_balance_generated", "=", True),
            ("account_id.is_off_balance", "=", False),
        ]
    )
    _logger.info(
        "%s lines to process for off-balance association.", len(on_balance_lines)
    )
    found = 0
    for line in on_balance_lines:
        on_balance_account = line.account_id
        off_balance_account = env["account.account"].search(
            [
                ("on_balance_account_id", "=", on_balance_account.id),
                ("is_off_balance", "=", True),
                ("company_ids", "=", line.company_id.id),
                ("internal_group", "=", "income"),
            ],
            limit=1,
        )
        product_id = line.product_id
        if off_balance_account and product_id:
            # Find related invoice line
            invoice_lines = env["account.move.line"].search(
                [
                    ("product_id", "=", product_id.id),
                    ("account_id", "=", off_balance_account.id),
                    ("partner_id", "=", line.partner_id.id),
                    ("move_id.payment_state", "in", ["partial", "paid"]),
                    ("last_payment", "=", line.date),
                ],
            )
            if invoice_lines:
                found += 1
                line.write(
                    {
                        "off_balance_line_ids": [
                            (4, invoice_line.id) for invoice_line in invoice_lines
                        ]
                    }
                )

    _logger.info("Associated %s off-balance lines.", found)
