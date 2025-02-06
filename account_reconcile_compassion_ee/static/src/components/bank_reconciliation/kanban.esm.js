/** @odoo-module **/

import { BankRecKanbanController } from "@account_accountant/components/bank_reconciliation/kanban";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(BankRecKanbanController.prototype, {
    getOne2ManyColumns() {
        const columns = super.getOne2ManyColumns(...arguments);
        const lineIdsRecords = this.state.bankRecRecordData.line_ids.records;

        if (lineIdsRecords.some((r) => r.data.product_id)) {
            const debit_col_index = columns.findIndex(
                (col) => col[0] === "account"
            );
            columns.splice(debit_col_index, 0, ["product", _t("Product")]);
        }
        if (lineIdsRecords.some((r) => r.data.contract_id)) {
            const debit_col_index = columns.findIndex(
                (col) => col[0] === "account"
            );
            columns.splice(debit_col_index, 0, ["contract", _t("Contract")]);
        }
        return columns;
    },
});
