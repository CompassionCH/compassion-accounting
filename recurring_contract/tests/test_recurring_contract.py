##############################################################################
#
#    Copyright (C) 2015-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Albert SHENOUDA <albert.shenouda@efrei.net>, Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import logging
import random
import string

from odoo.tests import TransactionCase

logger = logging.getLogger(__name__)


class BaseContractTest(TransactionCase):
    """Basic class that gives access to helpers to generate test contracts.

    It defines no test of its own: it is the fixture the contract tests of the
    other Compassion modules build upon.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, queue_job__no_delay=True))
        # The pricelist never varies, so one is enough for the whole class.
        cls.pricelist = cls.env["product.pricelist"].create(
            {
                "name": "global pricelist",
                "company_id": cls.env.company.id,
                "item_ids": [
                    (
                        0,
                        0,
                        {
                            "product_tmpl_id": False,
                            "base": "list_price",
                            "fixed_price": 10,
                            "applied_on": "3_global",
                        },
                    )
                ],
            }
        )

    def setUp(self):
        super().setUp()
        company_id = self.env.company.id
        self.env["ir.config_parameter"].set_param(
            f"recurring_contract.do_generate_curr_month_{company_id}", "False"
        )
        self.env["ir.config_parameter"].set_param(
            f"recurring_contract.invoice_block_day_{company_id}", 31
        )
        self.partner_1 = self.env.ref("base.res_partner_address_1")
        self.RecurringContractGroup = self.env["recurring.contract.group"]
        self.RecurringContract = self.env["recurring.contract"]
        self.payment_mode = self.env.ref(
            "account_payment_mode.payment_mode_inbound_ct2"
        )
        self.product = self.env.ref("product.product_product_1")

    def ref(self, length):
        return "".join(random.choice(string.ascii_lowercase) for _ in range(length))

    def create_group(self, vals):
        base_vals = {
            "advance_billing_months": 1,
            "payment_mode_id": self.payment_mode.id,
            "recurring_value": 1,
            "recurring_unit": "month",
        }
        base_vals.update(vals)
        return self.RecurringContractGroup.create(base_vals)

    def create_contract(self, vals, line_vals):
        name = self.ref(10)
        base_vals = {
            "reference": name,
            "state": "draft",
            "pricelist_id": self.pricelist.id,
            "contract_line_ids": [(0, 0, line) for line in line_vals],
        }
        for line in base_vals["contract_line_ids"]:
            if "product_id" not in line[2]:
                line[2]["product_id"] = self.product.id
            if "quantity" not in line[2]:
                line[2]["quantity"] = 1.0
        base_vals.update(vals)
        return self.RecurringContract.create(base_vals)

    def _pay_invoice(self, invoice):
        invoice.ensure_one()
        bank_journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", invoice.company_id.id)],
            limit=1,
        )
        # Generate payment with the wizard
        # (the context simulates what's done in the web interface)
        self.env["account.payment.register"].with_context(
            active_ids=invoice.ids, active_model=invoice._name
        ).create(
            {
                "journal_id": bank_journal.id,
                "amount": invoice.amount_total,
                "payment_date": invoice.invoice_date_due,
                "payment_method_line_id": (
                    bank_journal.inbound_payment_method_line_ids[0].id
                ),
                "partner_type": "customer",
            }
        ).action_create_payments()
