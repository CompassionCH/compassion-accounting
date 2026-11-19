##############################################################################
#
#    Copyright (C) 2026 Compassion CH (http://www.compassion.ch)
#
#    The licence is in the file __manifest__.py
#
##############################################################################
def clean_cardholder_name(name):
    """A name on the card as typed, cleaned for PayU and the database:
    control characters dropped (PostgreSQL refuses NUL), whitespace
    collapsed, 100 characters at most."""
    if not isinstance(name, str):
        return ""
    name = "".join(c for c in name if c.isprintable() or c.isspace())
    return " ".join(name.split())[:100]
