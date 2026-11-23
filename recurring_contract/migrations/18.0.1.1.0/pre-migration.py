import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

OLD_INVOICER_MODELS = ("recurring.invoicer.wizard", "recurring.invoicer")


def _remove_old_wizard_action(cr):
    """Remove the ir.actions.act_window action_invoice_automatic_generation.

    It is recreated as an ir.actions.server in recurring_contract_view.xml.
    Odoo refuses to update a record if its model changes, so it is deleted
    first. ir_act_window inherits from ir_actions in PostgreSQL, so no row is
    left behind in ir_actions.
    """
    cr.execute(
        """
        DELETE FROM ir_act_window
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'recurring_contract'
              AND name = 'action_invoice_automatic_generation'
              AND model = 'ir.actions.act_window'
        )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
        WHERE module = 'recurring_contract'
          AND name = 'action_invoice_automatic_generation'
          AND model = 'ir.actions.act_window'
        """
    )


def _adopt_invoice_generation_cron(cr):
    """Keep the existing invoicing cron instead of creating a new one.

    The cron data file is noupdate: once the old xmlid is renamed, the loader
    reuses the existing cron and keeps its state (active, nextcall, interval).
    """
    openupgrade.rename_xmlids(
        cr,
        [
            (
                "recurring_contract.recurring_invoicer_cron",
                "recurring_contract.invoice_generation_cron",
            )
        ],
    )
    # The old parent server action xmlid points to an unused action.
    # Point it to the server action of the adopted cron.
    cr.execute(
        """
        UPDATE ir_model_data imd
        SET name = 'invoice_generation_cron_ir_actions_server',
            res_id = c.ir_actions_server_id
        FROM ir_model_data cron_imd
        JOIN ir_cron c ON c.id = cron_imd.res_id
        WHERE imd.module = 'recurring_contract'
          AND imd.name = 'recurring_invoicer_cron_ir_actions_server'
          AND cron_imd.module = 'recurring_contract'
          AND cron_imd.name = 'invoice_generation_cron'
          AND cron_imd.model = 'ir.cron'
          AND NOT EXISTS (
              SELECT 1 FROM ir_model_data
              WHERE module = 'recurring_contract'
                AND name = 'invoice_generation_cron_ir_actions_server'
          )
        """
    )


def _repoint_invoicer_server_actions(cr):
    """Move the server actions of the old invoicer models to the contract group.

    This covers the daily cron, the "friday" cron of sponsorship_compassion
    (database-only) and any other action on the removed models. Without it,
    the removal of the old models would delete these crons. They all call
    generate_from_cron(), which recurring.contract.group provides with the
    same behaviour.
    """
    cr.execute(
        """
        UPDATE ir_act_server
        SET model_id = (
                SELECT id FROM ir_model WHERE model = 'recurring.contract.group'
            ),
            model_name = 'recurring.contract.group'
        WHERE model_name IN %s
        RETURNING id
        """,
        (OLD_INVOICER_MODELS,),
    )
    action_ids = tuple(row[0] for row in cr.fetchall())
    _logger.info("Moved server actions %s to recurring.contract.group", action_ids)
    if action_ids:
        # The stored cron name can be outdated: resync it with the action name.
        cr.execute(
            """
            UPDATE ir_cron c
            SET cron_name = a.name->>'en_US'
            FROM ir_act_server a
            WHERE a.id = c.ir_actions_server_id
              AND a.id IN %s
            """,
            (action_ids,),
        )


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    _remove_old_wizard_action(cr)
    _adopt_invoice_generation_cron(cr)
    _repoint_invoicer_server_actions(cr)
