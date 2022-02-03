# Copyright 2009-2019 Noviat.
# License LGPL-3 or later (http://www.gnu.org/licenses/lpgl).

from odoo import api, models, _
from odoo.addons.l10n_ch_payment_return_sepa.models.errors import\
    NoTransactionsError, FileAlreadyImported
from odoo.exceptions import UserError
import xml.etree.cElementTree as ET
import logging
import base64
_logger = logging.getLogger(__name__)


class EbicsFile(models.Model):
    _inherit = 'ebics.file'
    def _file_format_methods(self):
        """
        Extend this dictionary in order to add support
        for extra file formats.
        """
        res = {
            'pain.002.001.03':
                {'process': self._process_pain002,
                 'unlink': self._unlink_pain002},
            'pain.002':
                {'process': self._process_pain002,
                 'unlink': self._unlink_pain002},
        }
        res.update(super()._file_format_methods())
        
        return res

    @staticmethod
    def _process_pain002(self):
        """ convert the file to a record of model payment return."""
        _logger.info("Start import '%s'", self.name)
        try:
            import_module = 'l10n_ch_payment_return_sepa'
            self._check_import_module(import_module)
            values = {
                'data_file': self.data,
                'filename': self.name
            }
            pr_import_obj = self.env['payment.return.import']
            pr_wiz_imp = pr_import_obj.create(values)
            _logger.info("LOG import1 '%s'", pr_wiz_imp)
            import_result = pr_wiz_imp.import_file()
            _logger.info("LOG import2 '%s'", import_result)

            payment_return = self.env["payment.return"].browse(import_result['res_id'])
            # Mark the file as imported, remove binary as it should be
            # attached to the statement.
            _logger.info("LOG import3 '%s'", payment_return)
            self.write({
                'state': 'done',
                'payment_return_id': payment_return.id,
                'payment_order': payment_return.payment_order_id.id,
                'error_message': False
            })
            # Automatically confirm payment returns
            _logger.info("LOG import '%s'", 4)
            payment_return.action_confirm()
            _logger.info("[OK] import file '%s'", self.filename)
        except NoTransactionsError as e:
            _logger.info('Exception: NO TRANSACTION_______________')

            if e.object[0]['payment_order_id'] and not e.object[0]['transactions']:
                po = self.env['account.payment.order'].browse(e.object[0]['payment_order_id'])
                po.generated2uploaded()
            self.write({
                'state': 'done',
                'error_message': e.name
            })
        except FileAlreadyImported as e:
            _logger.info(e.name + "with file %s", self.name)
            references = [x['reference'] for x in e.object[0]['transactions']]
            payment_return = self.env['payment.return']\
                .search([('line_ids.reference', 'in', references)])
            self.write({
                'state': 'done',
                'payment_return_id': payment_return.id,
                'error_message': e.name
            })
        except UserError as e:
            # wrong parser used, raise the error to the parent so it's not
            # catch by the following except Exception
            _logger.info(
                "[FAIL] import file '%s' to bank Statements: UserError",
                self.name)
            self._on_error_parse_xml_and_cancel(e.name)

        except Exception as e:
            _logger.info(
                "[FAIL] import file '%s' to bank Statements",
                self.name,
                exc_info=True
            )
            self.env.cr.rollback()
            self.invalidate_cache()
            # Write the error in the postfinance file
            if self.state != 'error':
                self.write({
                    'state': 'draft',
                    'error_message': e.args and e.args[0]
                })
                # Here we must commit the error message otherwise it
                # can be unset by a next file producing an error
                # pylint: disable=invalid-commit
                self.env.cr.commit()
            self._on_error_parse_xml_and_cancel(e.name)

    def _on_error_parse_xml_and_cancel(self, err_message):
        _logger.info("Parsing file with err: %s", err_message)
        root = ET.fromstring(base64.b64decode(self.data))
        ns = root.tag[1:root.tag.index("}")]
        _logger.info("PAIN002 ns: %s", ns)
        po_name = root.find('./ns:CstmrPmtStsRpt/ns:OrgnlGrpInfAndSts/ns:OrgnlMsgId', namespaces={'ns': ns}).text
        _logger.info("PAIN002 po_name: %s", po_name)
        po_state = root.find('./ns:CstmrPmtStsRpt/ns:OrgnlGrpInfAndSts/ns:GrpSts', namespaces={'ns': ns}).text
        _logger.info("PAIN002 po_state: %s", po_state)
        payment_order = self.env['account.payment.order'].search([('name', '=', po_name)])
        _logger.info("PAIN002 payment_order: %s", payment_order)
        if payment_order.state == 'generated':
            if po_state == 'RJCT':
                _logger.info("RJCT payment order %s with the folowing err: %s", po_name, err_message)
                payment_order.action_cancel()
                payment_order.message_post(body = err_message)
            else:
                #partially rejected only
                _logger.info("Check if payment order is PART rjct")
                tx = root.findall('./ns:CstmrPmtStsRpt/ns:OrgnlPmtInfAndSts/ns:TxInfAndSts', namespaces={'ns': ns})
                for t in tx:
                    if t.find('./ns:TxSts', namespaces={'ns': ns}).text == 'RJCT':
                        #search for payment line
                        payment_line_ids = payment_order.bank_line_ids.filtered(
                            lambda r: r.name == t.find('./ns:OrgnlEndToEndId', namespaces={'ns': ns}).text)[0].payment_line_ids
                        _logger.info("PAIN002 payment_line_ids: %s", payment_line_ids)

                        #free line with message
                        rsn = t.findall('./ns:StsRsnInf/ns:AddtlInf', namespaces={'ns': ns})
                        rsn_text=[]
                        for r in rsn:
                            rsn_text.append(r.text)
                        payment_line_ids.free_line(' '.join(rsn_text))

                payment_order.generated2uploaded()
                self.write({
                    'state': 'done',
                    'error_message': err_message
                })



    def _unlink_pain002(self):
        """
        Placeholder for camt053 specific actions before removing the
        EBICS data file and its related bank statements.
        """
        pass
