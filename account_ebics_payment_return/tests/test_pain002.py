# Copyright 2026 Compassion CH (http://www.compassion.ch)
# License LGPL-3 or later (http://www.gnu.org/licenses/lpgl).

import base64

from odoo import fields
from odoo.tests import tagged

from odoo.addons.account_payment_order.tests.test_payment_order_outbound import (
    TestPaymentOrderOutboundBase,
)

PAIN002 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.002.001.03">
  <CstmrPmtStsRpt>
    <GrpHdr>
      <MsgId>STATUS-REPORT-1</MsgId>
      <CreDtTm>2026-10-23T10:00:00</CreDtTm>
    </GrpHdr>
    <OrgnlGrpInfAndSts>
      <OrgnlMsgId>{order_name}</OrgnlMsgId>
      <OrgnlMsgNmId>pain.001.001.03</OrgnlMsgNmId>
      <GrpSts>{status}</GrpSts>
      {reason}
    </OrgnlGrpInfAndSts>
    <OrgnlPmtInfAndSts>
      <OrgnlPmtInfId>1</OrgnlPmtInfId>
      {transactions}
    </OrgnlPmtInfAndSts>
  </CstmrPmtStsRpt>
</Document>
"""

TRANSACTION = """
      <TxInfAndSts>
        <OrgnlEndToEndId>{end_to_end_id}</OrgnlEndToEndId>
        <TxSts>{status}</TxSts>
        {reason}
      </TxInfAndSts>"""

REASON = """<StsRsnInf>
        <Rsn><Cd>{code}</Cd></Rsn>
        <AddtlInf>{info}</AddtlInf>
      </StsRsnInf>"""


@tagged("-at_install", "post_install")
class TestPain002(TestPaymentOrderOutboundBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pain002_format = (
            cls.env["ebics.file.format"]
            .sudo()
            .create(
                {
                    "name": "pain.002",
                    "type": "down",
                    "order_type": "Z01",
                    "download_process_method": "pain.002",
                }
            )
        )

    def _generate_order(self, same_partner=False):
        """Lines of the same partner are grouped in one payment (transaction)."""
        if not same_partner:
            self.invoice_02.partner_id = self.env["res.partner"].create(
                {"name": "Other Test Partner"}
            )
        invoices = self.invoice + self.invoice_02
        invoices.action_post()
        self.env["account.invoice.payment.line.multi"].with_context(
            active_model="account.move", active_ids=invoices.ids
        ).create({}).run()
        order = self.env["account.payment.order"].search(self.domain)
        order.journal_id = self.bank_journal
        order.draft2open()
        order.open2generated()
        return order

    def _payment_of(self, order, invoice):
        return order.payment_ids.filtered(
            lambda p: invoice in p.payment_line_ids.move_line_id.move_id
        )

    def _process(self, order_name, status, transactions="", reason=""):
        content = PAIN002.format(
            order_name=order_name,
            status=status,
            reason=reason,
            transactions=transactions,
        )
        ebics_file = self.env["ebics.file"].create(
            {
                "name": "pain002.xml",
                "date": fields.Datetime.now(),
                "format_id": self.pain002_format.id,
                "data": base64.b64encode(content.encode()),
            }
        )
        ebics_file.process()
        self.assertEqual(ebics_file.state, "done")
        return ebics_file

    def test_order_accepted(self):
        order = self._generate_order()
        ebics_file = self._process(order.name, "ACCP")
        self.assertEqual(order.state, "uploaded")
        self.assertFalse(order.payment_line_ids.filtered("returned"))
        self.assertIn("accepted", ebics_file.note_process)

    def test_order_rejected(self):
        order = self._generate_order()
        reason = REASON.format(code="FF01", info="Invalid file format")
        ebics_file = self._process(order.name, "RJCT", reason=reason)
        self.assertEqual(order.state, "cancel")
        self.assertIn("Invalid file format", ebics_file.note_process)
        self.assertIn("Invalid file format", order.message_ids[0].body)

    def test_transaction_rejected(self):
        order = self._generate_order()
        rejected = self._payment_of(order, self.invoice)
        accepted = self._payment_of(order, self.invoice_02)
        transactions = TRANSACTION.format(
            end_to_end_id=rejected.id,
            status="RJCT",
            reason=REASON.format(code="AC04", info="Account closed"),
        ) + TRANSACTION.format(end_to_end_id=accepted.id, status="ACCP", reason="")
        ebics_file = self._process(order.name, "PART", transactions)

        self.assertEqual(order.state, "uploaded")
        self.assertEqual(rejected.state, "canceled")
        self.assertNotEqual(accepted.state, "canceled")
        rejected_line = rejected.payment_line_ids
        self.assertTrue(rejected_line.returned)
        self.assertFalse(rejected_line.move_line_id)
        self.assertFalse(accepted.payment_line_ids.returned)
        self.assertIn("Account closed", ebics_file.note_process)

    def test_grouped_transaction_rejected(self):
        order = self._generate_order(same_partner=True)
        self.assertEqual(len(order.payment_ids), 1)
        transactions = TRANSACTION.format(
            end_to_end_id=order.payment_ids.id,
            status="RJCT",
            reason=REASON.format(code="AC04", info="Account closed"),
        )
        self._process(order.name, "PART", transactions)
        self.assertEqual(order.payment_ids.state, "canceled")
        self.assertEqual(len(order.payment_line_ids.filtered("returned")), 2)

    def test_rejected_transaction_reason_code_only(self):
        order = self._generate_order()
        rejected = self._payment_of(order, self.invoice)
        transactions = TRANSACTION.format(
            end_to_end_id=rejected.id,
            status="RJCT",
            reason="<StsRsnInf><Rsn><Cd>AC04</Cd></Rsn></StsRsnInf>",
        )
        ebics_file = self._process(order.name, "PART", transactions)
        self.assertEqual(rejected.state, "canceled")
        self.assertIn("AC04", ebics_file.note_process)

    def test_rejected_transaction_unknown(self):
        order = self._generate_order()
        transactions = TRANSACTION.format(
            end_to_end_id="not-a-payment", status="RJCT", reason=""
        )
        ebics_file = self._process(order.name, "PART", transactions)
        self.assertEqual(order.state, "uploaded")
        self.assertFalse(order.payment_line_ids.filtered("returned"))
        self.assertIn("not-a-payment", ebics_file.note_process)

    def test_order_not_found(self):
        ebics_file = self._process("UNKNOWN-ORDER", "RJCT")
        self.assertIn("UNKNOWN-ORDER", ebics_file.note_process)

    def test_order_already_cancelled(self):
        order = self._generate_order()
        order.action_cancel()
        ebics_file = self._process(order.name, "ACCP")
        self.assertEqual(order.state, "cancel")
        self.assertIn("nothing to do", ebics_file.note_process)

    def test_not_a_status_report(self):
        ebics_file = self.env["ebics.file"].create(
            {
                "name": "other.xml",
                "date": fields.Datetime.now(),
                "format_id": self.pain002_format.id,
                "data": base64.b64encode(b"<Document><Other/></Document>"),
            }
        )
        ebics_file.process()
        self.assertIn("not a payment status report", ebics_file.note_process)
