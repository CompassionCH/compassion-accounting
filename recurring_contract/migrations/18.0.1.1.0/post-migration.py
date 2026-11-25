import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    """Remove what Odoo leaves behind of the removed recurring.invoicer models.

    Odoo does not drop the tables of models that are no longer in the
    registry, so they are dropped here.
    """
    cr = env.cr
    cr.execute("ALTER TABLE account_move DROP COLUMN IF EXISTS recurring_invoicer_id")
    cr.execute("DROP TABLE IF EXISTS recurring_invoicer CASCADE")
    cr.execute("DROP TABLE IF EXISTS recurring_invoicer_wizard CASCADE")
    _logger.info("Dropped recurring_invoicer tables and account_move column")

    # Saved filters using the removed field (in their domain, grouping or
    # sorting) would raise an error when used.
    cr.execute(
        """
        DELETE FROM ir_filters
        WHERE domain LIKE %(f)s OR context LIKE %(f)s OR sort LIKE %(f)s
        RETURNING id
        """,
        {"f": "%recurring_invoicer_id%"},
    )
    _logger.info("Deleted saved filters %s", [row[0] for row in cr.fetchall()])
