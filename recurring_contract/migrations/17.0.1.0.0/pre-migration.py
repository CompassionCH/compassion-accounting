from openupgradelib import openupgrade


def migrate(cr, version):
    cr.execute(
        """
        SELECT id FROM ir_act_server
        WHERE name->>'en_US' = 'Contract line update on pricelist item end date'
    """
    )
    res_id = cr.fetchone()
    if res_id and res_id[0]:
        openupgrade.add_xmlid(
            cr,
            "recurring_contract",
            "action_pricelist_item_update",
            "ir.actions.server",
            res_id[0],
        )
