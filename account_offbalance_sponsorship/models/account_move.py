from odoo import models, api


class AccountMove(models.Model):
    _inherit = "account.move"

    def js_remove_outstanding_partial(self, partial_id):
        """Called by the 'payment' widget to remove a reconciled entry from the present invoice.

        :param partial_id: The id of an existing partial reconciliation linked to the current invoice.
        """

        self.ensure_one()
        partial = self.env["account.partial.reconcile"].browse(partial_id)

        if not partial:
            return False

        # Unreconcile
        res = super().js_remove_outstanding_partial(partial_id)

        # Get off-balance accounts
        off_rec, off_ass = self.line_ids.get_account_offbalance(self.company_id)
        account_32110 = self.env["account.account"].search([
            ("code", "=", "32110"),
            ("company_id", "=", self.company_id.id),
        ], limit=1).id

        # Need to set the move to draft so we can edit its move_lines
        self.write({"state": "draft"})

        # Get lines to remove
        lines_to_remove = self.line_ids.filtered(lambda line: line.account_id.id in [off_ass, account_32110])

        if lines_to_remove:
            lines_to_remove.unlink()

        # Set move as posted after removing the lines
        self.write({"state": "posted"})


        return res

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def get_account_offbalance(self, company):
        param_obj = self.env["res.config.settings"].with_company(company)
        return (
            param_obj.get_param("account_offbalance_receivable"),
            param_obj.get_param("account_offbalance_asset"),
        )

    @api.model
    def _reconcile_plan(self, reconciliation_plan):
        """
        Override _reconcile_plan
        Add additionnal account_move_line to meet nordics, offset balance accounting specification.

        """
        # Get the standard reconciliation plan
        plan_list, all_amls = self._optimize_reconciliation_plan(reconciliation_plan)

        for plan_node in plan_list:
            amls = plan_node['amls']

            # Check if customer accoutn is affected
            if any(aml.account_id.code.startswith("91") for aml in amls):
                # If so add the additional line for offeset balance
                self._add_off_balance_lines(plan_node)

        # Keep going with the standard logic
        move_container = {'records': all_amls.move_id}
        with all_amls.move_id._check_balanced(move_container), \
             all_amls.move_id._sync_dynamic_lines(move_container):
            self._reconcile_plan_with_sync(plan_list, all_amls)

    def _add_off_balance_lines(self, plan_node):
        """
        Creates offset balance account_move_lines

        :param plan_node: Dict containing reconciliation plan data.
        """
        company = plan_node['amls'][0].move_id.company_id
        #Retrieve accounts defines in the settings
        account_offbalance_receivable, account_offbalance_asset = self.get_account_offbalance(company)

        for aml in plan_node['amls']:
            if aml.account_id.code.startswith("91"):
                move = aml.move_id
                amount = aml.credit if aml.credit > 0 else 0.0

                # Check amount before creating hte account_move_lines
                if amount > 0:
                    self.env["account.move.line"].with_context(check_move_validity=False).create([
                        {
                            "account_id": account_offbalance_asset,
                            "name": "off-balance asset",
                            "move_id": move.id,
                            "partner_id": move.partner_id.id,
                            "debit": amount,
                            "credit": 0.0,
                        },
                        {
                            "account_id": self.env["account.account"].search([
                                ("code", "=", "32110"),
                                ("company_id", "=", company.id),
                            ], limit=1).id,
                            "name": "CDSP Sponsorship",
                            "move_id": move.id,
                            "partner_id": move.partner_id.id,
                            "debit": 0.0,
                            "credit": amount,
                        },
                    ])
