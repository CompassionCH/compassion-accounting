import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Remove stale ir.actions.act_window for action_invoice_automatic_generation.

    This action is recreated as ir.actions.server in recurring_contract_view.xml.
    Odoo refuses to update a record if the model type changes, so we delete it first.
    """
    cr.execute("""
        DELETE FROM ir_act_window
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'recurring_contract'
              AND name = 'action_invoice_automatic_generation'
              AND model = 'ir.actions.act_window'
        )
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'recurring_contract'
          AND name = 'action_invoice_automatic_generation'
          AND model = 'ir.actions.act_window'
    """)
    _logger.info(
        "pre-migration: removed stale act_window action_invoice_automatic_generation"
    )
