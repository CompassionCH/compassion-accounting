from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    if openupgrade.column_exists(env.cr, 'account_invoice_line_2_splitwizard', 'account_move_line_id'):
        openupgrade.rename_columns(
            env.cr, {'account_invoice_line_2_splitwizard': [('account_move_line_id', 'account_invoice_line_id')]}
        )
