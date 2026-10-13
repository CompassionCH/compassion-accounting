##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
##############################################################################
{
    "name": "Payment Provider: PayU GPO",
    "version": "18.0.1.0.0",
    "category": "Accounting/Payment Providers",
    "summary": "PayU GPO (secure.payu.com) with card tokens for recurring charges",
    "author": "Compassion CH, Odoo Community Association (OCA)",
    "website": "https://github.com/CompassionCH/compassion-accounting",
    "license": "AGPL-3",
    "depends": ["payment"],
    "data": [
        "views/payment_provider_views.xml",
        "views/payment_payu_gpo_templates.xml",
        "data/payment_provider_data.xml",
        "data/ir_cron_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_payu_gpo/static/src/js/payment_form.esm.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "development_status": "Alpha",
    "installable": True,
}
