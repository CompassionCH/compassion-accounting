# Copyright 2026 Compassion CH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Bank statement reconcile UTM",
    "summary": "Campaign, medium and source of the journal entries and of the "
    "bank statement lines in the reconciliation",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "website": "https://github.com/CompassionCH/compassion-accounting",
    "author": "Compassion CH",
    "license": "AGPL-3",
    "depends": ["account_reconcile_oca", "utm"],
    "data": [
        "views/account_move_views.xml",
        "views/account_bank_statement_line_views.xml",
    ],
    "installable": True,
}
