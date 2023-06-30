from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    if not version:
        return
    openupgrade.rename_fields(env, [
        ('account.statement.completion.rule', 'account_statement_completion_rule', 'function_to_call', {
            'field_name': 'python_completion_rule',
            'field_type': 'text',  # Change the data type to 'text'
        }),
    ])