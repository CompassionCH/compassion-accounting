/** @odoo-module **/

import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { AccountPaymentField } from "@account/components/account_payment_field/account_payment_field";
import { registry } from "@web/core/registry";

export class RecurringContractAccountPaymentField extends AccountPaymentField {
    setup() {
        super.setup();
    }

    getInfo() {
        const info = super.getInfo();
        for (const line of info.lines) {
            if (line.payment_date) {
                line.formattedPaymentDate = formatDate(
                    deserializeDate(line.payment_date)
                );
            }
        }
        return info;
    }
}

registry.category("fields").add(
    "payment",
    {
        ...registry.category("fields").get("payment"),
        component: RecurringContractAccountPaymentField,
    },
    { force: true }
);
