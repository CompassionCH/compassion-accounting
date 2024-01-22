from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # Precompute fields to speed up the migration
    openupgrade.add_fields(env, [
        ('last_payment', 'account.move', 'account_move', 'date', False, 'recurring_contract', False),
        ('missing_invoices', 'recurring.contract', 'recurring_contract', 'boolean', False, 'recurring_contract', False),
        ('due_invoice_ids', 'recurring.contract', 'recurring_contract', 'many2many', False, 'recurring_contract', False),
        ('amount_due', 'recurring.contract', 'recurring_contract', 'integer', False, 'recurring_contract', False),
        ('months_due', 'recurring.contract', 'recurring_contract', 'integer', False, 'recurring_contract', False),
    ])
    openupgrade.logged_query(env.cr,
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
    openupgrade.logged_query(env.cr,
"""INSERT INTO recurring_contract_due_invoice_rel (recurring_contract_id, account_move_id)
            SELECT DISTINCT aml.contract_id, aml.move_id
            FROM account_move_line aml
            JOIN account_move m ON m.id = aml.move_id
            WHERE aml.contract_id IS NOT NULL
            AND m.payment_state != 'paid' AND m.state = 'posted' AND aml.due_date < NOW()""")
