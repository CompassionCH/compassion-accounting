{
    'name': 'CAMT 054 import and reconcile',
    'version': '12.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Monzione Marco, Odoo Community Association (OCA)',
    'website': '...',
    'category': 'Banking addons',
    'depends': [
        'account_bank_statement_import_camt_details',
        'l10n_ch_fds_postfinance',
    ],
    'data': [
        'views/account_bank_statement_line_test.xml',
    ],
    'demo': [
        'demo/test_data.xml',
    ],
    'installable': True,
}
