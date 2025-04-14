from odoo import api, SUPERUSER_ID
from openupgradelib import openupgrade


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    off_balance_accounts = (
        env["account.account"]
        .search([("code", "like", "9"), ("account_type", "!=", "equity_unaffected")])
        .filtered(lambda a: a.code.startswith("9"))
    )
    for account in off_balance_accounts:
        linked_account = env["account.account"].search(
            [
                ("code", "=", account.code[1:]),
                ("company_id", "=", account.company_id.id),
            ],
            limit=1,
        )
        account.write(
            {
                "on_balance_account_id": linked_account.id,
                "is_off_balance": True,
            }
        )
    params_obj = env["ir.config_parameter"]
    for company in env["res.company"].search([]):
        off_balance_asset_account = params_obj.get_param(
            f"account_offbalance_asset_{company.id}"
        )
        if off_balance_asset_account:
            company.off_balance_asset_account_id = int(off_balance_asset_account)
    openupgrade.logged_query(
        env.cr,
        """DELETE FROM ir_config_parameter WHERE key LIKE 'account_offbalance_%'""",
    )
    openupgrade.logged_query(
        env.cr,
        """UPDATE account_move_line l
        SET is_off_balance_generated = true,
        name = 'Off-Balance Adjustment'
        FROM account_move m
        WHERE l.move_id = m.id
        AND l.name = m.name
        """,
    )
    for company in env["res.company"].search([]):
        curr_exch_accounts = (
            company.expense_currency_exchange_account_id
            + company.income_currency_exchange_account_id
        )
        for curr_exch_account in curr_exch_accounts:
            off_balance_exch_account = env["account.account"].search(
                [("on_balance_account_id", "=", curr_exch_account.id)], limit=1
            )
            if not off_balance_exch_account:
                curr_exch_account.copy(
                    {
                        "code": "9" + curr_exch_account.code,
                        "is_off_balance": True,
                        "on_balance_account_id": curr_exch_account.id,
                    }
                )
