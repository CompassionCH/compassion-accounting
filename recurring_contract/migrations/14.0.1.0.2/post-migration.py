
def migrate(cr, version):
    if version:
        cr.execute(
            "update recurring_contract_group set invoice_day = CAST(EXTRACT(day FROM recurring_contract.next_invoice_date) as varchar) "
            "from recurring_contract_group c "
            "inner join recurring_contract on group_id = c.id"
        )
