from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # Precompute fields to speed up the migration
    openupgrade.add_fields(
        env,
        [
            (
                "last_payment",
                "account.move",
                "account_move",
                "date",
                False,
                "recurring_contract",
                False,
            ),
            (
                "last_payment",
                "account.move.line",
                "account_move_line",
                "date",
                False,
                "recurring_contract",
                False,
            ),
            (
                "payment_state",
                "account.move.line",
                "account_move_line",
                "selection",
                False,
                "recurring_contract",
                False,
            ),
            (
                "missing_invoices",
                "recurring.contract",
                "recurring_contract",
                "boolean",
                False,
                "recurring_contract",
                False,
            ),
        ],
    )
    openupgrade.logged_query(
        env.cr,
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
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE account_move_line aml
        SET last_payment = (
            SELECT last_payment
            FROM account_move
            WHERE id = aml.move_id
        ),
        payment_state = (
            SELECT payment_state
            FROM account_move
            WHERE id = aml.move_id
        )
        WHERE move_id IS NOT NULL;
        """,
    )
    if not openupgrade.table_exists(env.cr, "account_move_recurring_contract_rel"):
        openupgrade.logged_query(
            env.cr,
            """
            ALTER TABLE account_invoice_recurring_contract_rel
                RENAME TO account_move_recurring_contract_rel;
            ALTER TABLE account_move_recurring_contract_rel
                ADD COLUMN account_move_id INTEGER;
            UPDATE account_move_recurring_contract_rel rel SET account_move_id = m.id
            FROM account_move m
            WHERE m.old_invoice_id = rel.account_invoice_id;
        """,
        )
