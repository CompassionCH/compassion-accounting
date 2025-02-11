from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def js_remove_outstanding_partial(self, partial_id):
        """Called by the 'payment' widget to remove a reconciled
         entry from the current invoice.

        :param partial_id: The id of an existing partial
         reconciliation linked to the current invoice.
        """

        self.ensure_one()
        partial = self.env["account.partial.reconcile"].browse(partial_id)

        if not partial:
            return False

        # Unreconcile
        res = super().js_remove_outstanding_partial(partial_id)

        # Get off-balance accounts
        off_rec, off_ass = self.line_ids.get_account_offbalance(self.company_id)

        # Set the move to draft so its move_lines can be edited
        self.write({"state": "draft"})

        ## Retrieve lines to remove
        # One of the lines is the one linked to off_ass.
        # The others are identified by their name.

        # Identify lines to remove
        lines_to_remove = self.line_ids.filtered(lambda line: line.name == self.name)
        if lines_to_remove:
            lines_to_remove.unlink()

        # Undo reconciliation for the statement lines
        st_lines = self.statement_line_ids
        for line in st_lines:
            line.action_undo_reconciliation()

        return res


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def get_account_offbalance(self, company):
        """
        Retrieves the off-balance accounts defined in
        the settings for the given company.
        Returns a tuple (account_offbalance_receivable,
        account_offbalance_asset).
        """
        param_obj = self.env["res.config.settings"].with_company(company)
        return (
            param_obj.get_param("account_offbalance_receivable"),
            param_obj.get_param("account_offbalance_asset"),
        )

    @api.model
    def _reconcile_plan(self, reconciliation_plan):
        """
        Override of _reconcile_plan.
        Adds additional account.move.line entries to comply
        with the Nordic offset balance specification.
        """
        # Retrieve the standard plan and all related AMLs
        plan_list, all_amls = self._optimize_reconciliation_plan(reconciliation_plan)

        # Determine the company from one of the AMLs
        company = all_amls and all_amls[0].company_id or self.env.company
        move = all_amls.move_id

        # Retrieve the off-balance receivable account defined in the settings
        account_offbalance_receivable, _ = self.get_account_offbalance(company)

        # If AML corresponds to the off-balance receivable account
        if any(aml.account_id.id == account_offbalance_receivable for aml in all_amls):
            self._add_off_balance_lines(move, company)

        # Continue with the standard reconciliation logic
        move_container = {"records": all_amls.move_id}
        with all_amls.move_id._check_balanced(
            move_container
        ), all_amls.move_id._sync_dynamic_lines(move_container):
            return self._reconcile_plan_with_sync(plan_list, all_amls)

    def _add_off_balance_lines(self, move, company):
        (
            account_offbalance_receivable,
            account_offbalance_asset,
        ) = self.get_account_offbalance(company)

        # Separate the invoice and the payment in the move
        invoice = move.filtered(lambda m: m.move_type == "out_invoice")
        payment_entry = move.filtered(lambda m: m.move_type == "entry")
        residual_amount = invoice.amount_residual

        # Retrieve the payment lines linked to the off-balance receivable account,
        # excluding the open balance line
        payment_lines = payment_entry.line_ids.filtered(
            lambda line: line.account_id.id == account_offbalance_receivable
            and "open balance" not in (line.name or "").lower()
        )
        payment_amount = sum(payment_lines.mapped("credit"))

        invoice_lines = invoice.line_ids

        # Dictionary for account code and amount for each line
        sponsorship_lines = {}

        # Get affected lines
        for line in invoice_lines.filtered(
            lambda invl: invl.account_id
            and invl.account_id.id != account_offbalance_receivable
            and invl.account_id.code.startswith("9")
        ):
            # Get line amount
            amount = line.credit if line.credit > 0 else 0.0
            if amount > 0:
                # Remove "9" from the account code
                # and retrieve the corresponding account
                new_code = line.account_id.code[1:]
                sponsorship_account = self.env["account.account"].search(
                    [
                        ("code", "=", new_code),
                        ("company_id", "=", company.id),
                    ],
                    limit=1,
                )
                if sponsorship_account:
                    sponsorship_lines.setdefault(sponsorship_account.id, []).append(
                        amount
                    )

        # Get the ratio to adjust the amount based on the payment made
        ratio = payment_amount / residual_amount if residual_amount else 0.0

        # Calculate the prorated and rounded amounts for each sponsorship line
        lines_to_create = []
        total_prorated = 0.0
        for sponsorship_account_id, amounts in sponsorship_lines.items():
            for amt in amounts:
                prorated_amount = amt * ratio
                # Round to the nearest tenth
                rounded_amount = round(prorated_amount, 1)
                lines_to_create.append(
                    {
                        "account_id": sponsorship_account_id,
                        "amount": rounded_amount,
                    }
                )
                total_prorated += rounded_amount

        diff = round(payment_amount - total_prorated, 1)
        if lines_to_create:
            lines_to_create[-1]["amount"] += diff
            total_prorated += diff

        # Create an account_move_line
        for line_dict in lines_to_create:
            self.env["account.move.line"].with_context(
                check_move_validity=False
            ).create(
                {
                    "account_id": line_dict["account_id"],
                    "name": payment_entry.name,
                    "move_id": payment_entry.id,
                    "partner_id": move.partner_id.id,
                    "debit": 0.0,
                    "credit": line_dict["amount"],
                }
            )

        # Create an account_move_line reflecting
        # the reconciliation amount on account_offbalance_asset
        self.env["account.move.line"].with_context(check_move_validity=False).create(
            {
                "account_id": account_offbalance_asset,
                "name": payment_entry.name,
                "move_id": payment_entry.id,
                "partner_id": move.partner_id.id,
                "debit": round(total_prorated, 1),
                "credit": 0.0,
            }
        )

        return True
