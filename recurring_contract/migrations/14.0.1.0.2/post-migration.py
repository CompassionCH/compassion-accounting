
def migrate(cr, version):
    if version:
        cr.execute(
            "update recurring_contract_group "
            "set invoice_day = COALESCE(CAST(EXTRACT(day FROM recurring_contract.next_invoice_date) as varchar), '1')"
            "from recurring_contract_group c "
            "inner join recurring_contract on group_id = c.id"
        )
