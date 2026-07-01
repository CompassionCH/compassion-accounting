import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Drop recurring.invoicer: remove FK column from account_move and drop table."""
    cr.execute(
        "ALTER TABLE account_move DROP COLUMN IF EXISTS recurring_invoicer_id"
    )
    _logger.info(
        "post-migration: dropped recurring_invoicer_id column (%s rows affected)",
        cr.rowcount,
    )

    cr.execute("DROP TABLE IF EXISTS recurring_invoicer CASCADE")
    _logger.info("post-migration: dropped recurring_invoicer table")
