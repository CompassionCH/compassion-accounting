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
            UPDATE recurring_contract_group
            SET company_id = COALESCE((
                SELECT company_id
                FROM recurring_contract
                WHERE group_id = recurring_contract_group.id
                ORDER BY state ASC
                LIMIT 1
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
