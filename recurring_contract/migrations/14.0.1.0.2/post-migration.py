def migrate(cr, version):
    if version:
        cr.execute(
            """
        update recurring_contract_group
        set invoice_suspended_until = (
            select date_trunc('month', min(next_invoice_date)) from recurring_contract
            where group_id = recurring_contract_group.id
            and state in ('waiting','active')
            and child_id is not null
            and next_invoice_date > (
                CURRENT_DATE +
                INTERVAL '1 month' * recurring_contract_group.advance_billing_months +
                INTERVAL '1 month'
            )
            group by group_id
            having count(*) = 1)
        """
        )
        cr.execute(
            """
            ALTER TABLE account_move_recurring_contract_rel
            DROP COLUMN account_invoice_id;
        """
        )
        cr.execute(
            """INSERT INTO account_move_recurring_contract_rel (recurring_contract_id,
                    account_move_id)
                 SELECT DISTINCT aml.contract_id, aml.move_id
                 FROM account_move_line aml
                 JOIN account_move m ON m.id = aml.move_id
                 WHERE aml.contract_id IS NOT NULL
                 AND m.payment_state != 'paid' AND m.state = 'posted'
                 AND aml.due_date < NOW()""",
        )
