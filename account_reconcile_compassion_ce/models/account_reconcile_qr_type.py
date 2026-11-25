from odoo import fields, models


class AccountReconcileQrType(models.Model):
    """T3622 Type of a QR (BVR) reference: its 22nd digit (see the
    Code_ref_QR (BVR) layout). Reconcile rules choose the types they handle."""

    _name = "account.reconcile.qr.type"
    _description = "QR reference type"
    _order = "code"

    code = fields.Char(required=True, size=1, help="22nd digit of the reference")
    name = fields.Char(required=True, translate=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "A QR reference type code must be unique.")
    ]
