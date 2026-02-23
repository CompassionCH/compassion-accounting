from openupgradelib import openupgrade


def migrate(cr, version):
    # Avoids unnecessary recomputation of due dates for all contracts
    # at the moment of the migration, as it can be a costly operation.
    # The field will be computed on demand when needed.
    if not openupgrade.column_exists(
        cr, "recurring_contract", "last_months_due_computed_at"
    ):
        openupgrade.logged_query(
            cr,
            """
            ALTER TABLE recurring_contract
            ADD COLUMN last_months_due_computed_at TIMESTAMP WITHOUT TIME ZONE
        """,
        )
