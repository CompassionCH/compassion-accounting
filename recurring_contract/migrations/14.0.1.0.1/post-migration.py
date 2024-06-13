from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    if not version:
        return
    # Restore contract_id value on move lines
    openupgrade.logged_query(
        env.cr,
        """
        update account_move_line m
        set contract_id=i.contract_id
        from account_invoice_line i
        where m.contract_id is null and old_invoice_line_id = i.id
        and i.contract_id is not null;
        """,
    )
    for contract in env["recurring.contract"].search(
        [("pricelist_id", "=", False), ("state", "not in", ["terminated", "cancelled"])]
    ):
        contract.on_change_company_id()
