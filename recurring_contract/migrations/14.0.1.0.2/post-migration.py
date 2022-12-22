
def migrate(cr, version):
    if version:
        cr.execute(
            "UPDATE recurring_contract SET invoice_day = EXTRACT(day FROM next_invoice_date)"
        )
