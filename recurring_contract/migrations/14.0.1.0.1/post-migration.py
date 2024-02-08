from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    if not version:
        return
    for contract in env["recurring.contract"].search(
        [("pricelist_id", "=", False), ("state", "not in", ["terminated", "cancelled"])]
    ):
        contract.on_change_company_id()
