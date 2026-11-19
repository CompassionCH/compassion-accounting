# Copyright 2009-2019 Noviat.
# License LGPL-3 or later (http://www.gnu.org/licenses/lpgl).

import base64
import logging

from lxml import etree

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

REJECTED = "RJCT"


class EbicsFile(models.Model):
    _inherit = "ebics.file"

    def _process_pain002(self):
        """
        Apply a payment status report (pain.002) to the payment order it answers:
        a rejected order is cancelled, the rejected transactions of an accepted
        order are freed from it. Problems are written in the process notes instead
        of raised, so that a batch import still processes the next files.
        """
        self.ensure_one()
        _logger.info("Process pain.002 file '%s'", self.name)
        try:
            notes = self._apply_pain002()
        except (UserError, etree.XMLSyntaxError) as e:
            _logger.warning("pain.002 file '%s' not processed: %s", self.name, e)
            notes = [self.env._("File not processed: %s") % e]
        self.note_process = "\n".join(notes)

    def _apply_pain002(self):
        if not self.data:
            raise UserError(self.env._("The file is empty."))
        root = etree.fromstring(
            base64.b64decode(self.data),
            parser=etree.XMLParser(resolve_entities=False, no_network=True),
        )
        group = root.find("{*}CstmrPmtStsRpt/{*}OrgnlGrpInfAndSts")
        if group is None:
            raise UserError(self.env._("This is not a payment status report."))
        order_name = group.findtext("{*}OrgnlMsgId")
        order = self.env["account.payment.order"].search(
            [("name", "=", order_name)], limit=1
        )
        if not order:
            raise UserError(self.env._("Payment order %s was not found.") % order_name)
        if order.state not in ("generated", "uploaded"):
            return [
                self.env._("Payment order %(order)s is %(state)s: nothing to do.")
                % {"order": order.name, "state": order.state}
            ]

        group_status = group.findtext("{*}GrpSts")
        if group_status == REJECTED:
            reason = self._get_pain002_reason(group)
            order.action_cancel()
            order.message_post(
                body=self.env._("Payment order rejected by the bank: %s") % reason
            )
            return [
                self.env._("Payment order %(order)s rejected and cancelled: %(rsn)s")
                % {"order": order.name, "rsn": reason}
            ]

        # Post the order first: posting it after freeing lines would post
        # the cancelled payments again.
        if order.state == "generated":
            order.generated2uploaded()
        notes = [
            self.env._("Payment order %(order)s accepted by the bank (%(status)s).")
            % {"order": order.name, "status": group_status}
        ]
        for transaction in root.iterfind(".//{*}OrgnlPmtInfAndSts/{*}TxInfAndSts"):
            if transaction.findtext("{*}TxSts") == REJECTED:
                notes.append(self._free_rejected_transaction(order, transaction))
        return notes

    def _free_rejected_transaction(self, order, transaction):
        """The EndToEndId of a transaction is the id of its account.payment."""
        end_to_end_id = (transaction.findtext("{*}OrgnlEndToEndId") or "").strip()
        reason = self._get_pain002_reason(transaction)
        payment = order.payment_ids.filtered(lambda p: str(p.id) == end_to_end_id)
        if not payment:
            message = self.env._(
                "Rejected transaction %(ref)s not found in the order: %(rsn)s"
            ) % {"ref": end_to_end_id, "rsn": reason}
            order.message_post(body=message)
            return message
        # The same rejection can be reported again: free each line only once.
        lines = payment.payment_line_ids.filtered(lambda line: not line.returned)
        if not lines:
            return self.env._(
                "Rejected payment %(payment)s was already freed: %(rsn)s"
            ) % {"payment": payment.name, "rsn": reason}
        try:
            with self.env.cr.savepoint():
                lines.free_line(reason)
        except UserError as e:
            message = self.env._(
                "Rejected payment %(payment)s could not be freed (%(err)s): %(rsn)s"
            ) % {"payment": payment.name, "err": e, "rsn": reason}
            order.message_post(body=message)
            return message
        return self.env._("Rejected payment %(payment)s freed: %(rsn)s") % {
            "payment": payment.name,
            "rsn": reason,
        }

    def _get_pain002_reason(self, node):
        """Additional information of the status reason, or its code."""
        reason = " ".join(
            (info.text or "").strip()
            for info in node.iterfind("{*}StsRsnInf/{*}AddtlInf")
        ).strip()
        return (
            reason
            or node.findtext("{*}StsRsnInf/{*}Rsn/{*}Cd")
            or self.env._("no reason given")
        )

    def _unlink_pain002(self):
        """Nothing is linked to a pain.002 file."""
