from base64 import b64encode

from odoo import Command, models


class AccountBankStmtImportCSV(models.TransientModel):
    _inherit = "base_import.import"

    def execute_import(self, fields, columns, options, dryrun=False):
        res = super().execute_import(fields, columns, options, dryrun)
        if options.get("bank_stmt_import"):
            for message in res.get("messages", []):
                if isinstance(message, dict):
                    statement_id = message.get("statement_id")
                    if statement_id:
                        statement = self.env["account.bank.statement"].browse(
                            statement_id
                        )
                        statement.write(
                            {
                                "attachment_ids": [
                                    Command.create(
                                        {
                                            "res_model": "account.bank.statement",
                                            "res_id": statement_id,
                                            "name": self.file_name,
                                            "datas": b64encode(self.file),
                                        }
                                    )
                                ]
                            }
                        )
        return res
