from odoo import models


class AccountReconcileAbstract(models.AbstractModel):
    _inherit = "account.reconcile.abstract"

    def _get_reconcile_line(
        self,
        line,
        kind,
        is_counterpart=False,
        max_amount=False,
        from_unreconcile=False,
        move=False,
        is_reconciled=False,
    ):
        vals = super()._get_reconcile_line(
            line,
            kind,
            is_counterpart=is_counterpart,
            max_amount=max_amount,
            from_unreconcile=from_unreconcile,
            move=move,
            is_reconciled=is_reconciled,
        )
        if line._name == "account.move.line":
            vals[0]["product_id"] = (
                line.product_id and [line.product_id.id, line.product_id.display_name]
            ) or False
            vals[0]["contract_id"] = (
                line.contract_id and [line.contract_id.id, line.contract_id.display_name]
            ) or False
        return vals


