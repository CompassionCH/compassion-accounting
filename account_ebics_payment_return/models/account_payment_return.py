# Copyright 2009-2019 Noviat.
# License LGPL-3 or later (http://www.gnu.org/licenses/lpgl).

from odoo import api, models, _
from odoo.addons.l10n_ch_payment_return_sepa.models.errors import\
    NoTransactionsError, FileAlreadyImported
from odoo.exceptions import UserError
import logging
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
            import_result = pr_wiz_imp.import_file()

            payment_return = self.env["payment.return"].browse(import_result['res_id'])
            # Mark the file as imported, remove binary as it should be
            # attached to the statement.
            self.write({
                'state': 'done',
                'payment_return_id': payment_return.id,
                'payment_order': payment_return.payment_order_id.id,
                'error_message': False
            })
            # Automatically confirm payment returns
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
            _logger.info(e.name, self.name)
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
            raise e
        except Exception as e:
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
            _logger.error(
                "[FAIL] import file '%s' to bank Statements",
                self.name,
                exc_info=True
            )
    def _unlink_pain002(self):
        """
        Placeholder for camt053 specific actions before removing the
        EBICS data file and its related bank statements.
        """
        pass
