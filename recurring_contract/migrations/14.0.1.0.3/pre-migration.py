from openupgradelib import openupgrade


def migrate(cr, version):
    # Precompute last_payment to speed up the migration
    if not openupgrade.column_exists(cr, "recurring_contract", "missing_invoices"):
        cr.execute(
            """
            ALTER TABLE recurring_contract
            ADD COLUMN missing_invoices bool
            """
        )
    cr.execute(
        """
        UPDATE recurring_contract c
        SET missing_invoices = false;
        """
    )
