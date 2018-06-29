{
    'name': 'CAMT 054 import and reconcile',
    'version': '10.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Monzione Marco',
    'website': '...',
    'category': 'Banking addons',
    'depends': [
        'account_bank_statement_import_camt_details',
        'l10n_ch_fds_postfinance',
        'account_payment_line_cancel',
    ],
    'data': [
        'views/account_bank_statement_line_test.xml',
    ],
    'demo': [

    ],
    'test': [
        'res/test_data.yml',
    ],
    'installable': True,
}
