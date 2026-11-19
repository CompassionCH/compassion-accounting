from . import controllers
from . import models

from odoo.addons.payment import setup_provider, reset_payment_provider

from .const import PROVIDER_CODE


def post_init_hook(env):
    setup_provider(env, PROVIDER_CODE)


def uninstall_hook(env):
    reset_payment_provider(env, PROVIDER_CODE)
