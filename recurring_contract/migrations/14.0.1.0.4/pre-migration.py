
def migrate(cr, version):
    if version:
        cr.execute(
            "update account_move set invoice_date = date, invoice_date_due = date where invoice_date is null"
        )
