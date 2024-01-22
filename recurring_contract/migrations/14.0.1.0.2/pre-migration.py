from openupgradelib import openupgrade


def migrate(cr, version):
    # Precompute last_payment to speed up the migration
    if not openupgrade.column_exists(cr, "account_move", "last_payment"):
        cr.execute(
            """
            ALTER TABLE account_move
            ADD COLUMN last_payment date
            """
        )
    cr.execute(
        """
        UPDATE account_move m
        SET last_payment = (
            SELECT MAX(date)
            FROM account_move_line aml
            WHERE (CASE 
                WHEN m.move_type = 'out_invoice' THEN aml.credit
                WHEN m.move_type = 'in_invoice' THEN aml.debit
                ELSE 0
            END) > 0 AND full_reconcile_id = ANY(
                SELECT full_reconcile_id
                FROM account_move_line
                WHERE move_id = m.id
            )
        )
        WHERE payment_state = 'paid' AND move_type IN ('out_invoice', 'in_invoice');
        """
    )
