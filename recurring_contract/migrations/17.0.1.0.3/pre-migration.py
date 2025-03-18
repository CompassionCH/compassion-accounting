from openupgradelib import openupgrade


def migrate(cr, version):
    if not openupgrade.column_exists(cr, "recurring_contract_group", "company_id"):
        openupgrade.logged_query(
            cr,
            """
            ALTER TABLE recurring_contract_group
            ADD COLUMN company_id INT
        """,
        )
        openupgrade.logged_query(
            cr,
            """
            UPDATE recurring_contract_group g
            SET company_id = COALESCE((
                SELECT company_id
                FROM recurring_contract
                WHERE group_id = g.id
                ORDER BY state ASC
                LIMIT 1
            ), (
                SELECT MAX(p.company_id)
                FROM recurring_contract c
                JOIN product_pricelist p ON c.pricelist_id = p.id
                WHERE c.group_id = g.id
            ), 1)
        """,
        )
        openupgrade.logged_query(
            cr,
            """
            ALTER TABLE recurring_contract_group
            ALTER COLUMN company_id SET NOT NULL
        """,
        )
    if not openupgrade.column_exists(cr, "recurring_contract_group", "pricelsit_id"):
        openupgrade.logged_query(
            cr,
            """
            ALTER TABLE recurring_contract_group
            ADD COLUMN pricelist_id INT
        """,
        )
        openupgrade.logged_query(
            cr,
            """
            UPDATE recurring_contract_group g
            SET pricelist_id = (
                SELECT pricelist_id
                FROM recurring_contract
                WHERE group_id = g.id
                ORDER BY state ASC
                LIMIT 1
            )
        """,
        )
