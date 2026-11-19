# Copyright 2009-2019 Compassion.
# License LGPL-3 or later (http://www.gnu.org/licenses/lpgl).

# pylint: disable=C8101
{
    "name": "Process Payment Order status reports downloaded via EBICS",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "author": "Compassion CH",
    "website": "https://github.com/CompassionCH/compassion-accounting",
    "category": "Accounting & Finance",
    "depends": [
        "account_ebics",
        "account_payment_line_free",
    ],
    "installable": True,
}
