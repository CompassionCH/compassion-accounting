# Copyright 2009-2019 Compassion.
# License LGPL-3 or later (http://www.gnu.org/licenses/lpgl).

{
    "name": "Download Payment Order return via EBICS",
    "version": "14.0.1.0.0",
    "license": "LGPL-3",
    "author": "Compassion",
    "category": "Accounting & Finance",
    "depends": [
        "account_ebics",
        "account_payment_line_free",
        "account_payment_return_import",
        "account_payment_return_import_pain_ch"  # l10n-switzerland
    ],
    "data": [
        #        'views/account_payment_order.xml',
    ],
    "installable": True,
}
