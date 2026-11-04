import { BankRecKanbanController } from "@account_accountant/components/bank_reconciliation/kanban";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(BankRecKanbanController.prototype, {
    getOne2ManyColumns() {
        const columns = super.getOne2ManyColumns(...arguments);
        const lineIdsRecords = this.state.bankRecRecordData.line_ids.records;

        if (lineIdsRecords.some((r) => r.data.product_id)) {
            const debit_col_index = columns.findIndex(
                (col) => col[0] === "account",
            );
            columns.splice(debit_col_index, 0, ["product", _t("Product")]);
        }
        if (lineIdsRecords.some((r) => r.data.contract_id)) {
            const debit_col_index = columns.findIndex(
                (col) => col[0] === "account",
            );
            columns.splice(debit_col_index, 0, ["contract", _t("Contract")]);
        }
        return columns;
    },

    /**
     * T2764 Keep the "Match Existing Entries" list in sync with the partner chosen
     * in the "Manual Operations" tab. The embedded list only receives its partner
     * filter when the statement line is mounted, and restores its previous search
     * facets afterwards, so a partner selected later was never applied.
     * @override
     */
    async actionLineChanged(fieldName) {
        await super.actionLineChanged(...arguments);
        if (fieldName !== "partner_id") {
            return;
        }
        const amls = this.state.bankRecEmbeddedViewsData?.amls;
        const partner = this.getBankRecRecordLineInEdit()?.data.partner_id;
        if (!amls) {
            return;
        }
        const context = { ...amls.context };
        if (partner) {
            context.search_default_partner_id = partner[0];
        } else {
            delete context.search_default_partner_id;
        }
        amls.context = context;
        // Drop the saved facets so that the default partner facet is applied
        delete amls.exportState;
    },
});
