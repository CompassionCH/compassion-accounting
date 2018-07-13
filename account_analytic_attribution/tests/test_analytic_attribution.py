# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2018 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Nicolas Bornand
#
#    The licence is in the file __manifest__.py
#
##############################################################################
import logging
from datetime import datetime, timedelta
from odoo import fields
from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestAnalyticAttribution(TransactionCase):

    def setUp(self):
        super(TestAnalyticAttribution, self).setUp()
        self.analytic_account = self.env["account.analytic.account"] \
            .create({"name": "Test Account"})
        self.account = self.env["account.account"] \
            .search([('code', '=', '1050')])
        self.tag = self.env.ref('account_analytic_attribution.tag_attribution')
        self.Attribution = self.env['account.analytic.attribution']

    def test_perform_distribution__line_generation(self):
        self._create_line_with_amount_twelve(self.analytic_account)
        self._create_line_with_amount_twelve(self.analytic_account)
        attribution = self.Attribution.create({})
        self.env['account.analytic.distribution.line'].create({
            'rate': 40,
            'account_analytic_id': self.analytic_account.id,
            'attribution_id': attribution.id
        })

        self._assert_analytic_lines_count(2)
        line = attribution.perform_distribution()
        self._assert_analytic_lines_count(3)

        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.amount, 9.6)  # 40% of (2*12)
        self.assertEqual(line.account_id.id, self.analytic_account.id)
        self.assertTrue('Analytic attribution for' in line.name)

    def test_perform_distribution__should_evict_old_analytic_lines(self):
        line = self._create_line_with_amount_twelve(self.analytic_account)
        line.tag_ids += self.env \
            .ref('account_analytic_attribution.tag_attribution')
        attribution = self.Attribution.create({})

        self._assert_analytic_lines_count(1)
        attribution.perform_distribution()
        self._assert_analytic_lines_count(0)

    def test_get_attribution__match_if_filters_are_not_set(self):
        attribution = self.Attribution.create({})
        self.env['account.analytic.distribution.line'].create({
            'rate': 40,
            'account_analytic_id': self.analytic_account.id,
            'attribution_id': attribution.id
        })

        matched = attribution.get_attribution(False, False, datetime.now())
        self.assertEqual(len(matched), 1)

    def test_get_attribution__matching_by_date(self):
        attribution = self.Attribution.create({
            'rate': 40,
            'date_start': datetime.now(),
            'date_stop': datetime.now()
        })

        yesterday = datetime.now() - timedelta(days=-1)
        rules = attribution.get_attribution(False, False, yesterday)
        self.assertEqual(len(rules), 0)

        matched = attribution.get_attribution(False, False, datetime.now())
        self.assertEqual(len(matched), 1)

    def test_get_attribution__matching_by_tag(self):
        attribution = self.Attribution.create({
            'rate': 40
        })
        attribution.analytic_tag_id += self.tag

        now = datetime.now()
        unknown_tag = 99
        rules = attribution.get_attribution(False, [unknown_tag], now)
        self.assertEqual(len(rules), 0)

        matched = attribution.get_attribution(False, [self.tag.id], now)
        self.assertEqual(len(matched), 1)

    def _create_line_with_amount_twelve(self, account):
        return self.env['account.analytic.line'].create({
            'name': 'test line',
            'amount': 12.0,
            'account_id': account.id,
            'general_account_id': 1,
            'date': fields.Datetime.from_string('2017-05-05')
        })

    def _assert_analytic_lines_count(self, count):
        lines_after = self.env['account.analytic.line'].search([])
        self.assertEqual(len(lines_after), count)
