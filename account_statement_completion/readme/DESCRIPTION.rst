This module adds a way to implement methods that will enrich the bank
statement lines imported and give an easy way to add custom completion
rules in sub-modules.

A completion rule can be attached to a journal for it to be launched when
a bank statement is imported for the journal.

It comes with two generic rules :

    1. Find a partner from the reference, if a move line exists with the
       same reference.
    2. Completion method for finding supplier invoices based the amount.

If more than one rule are defined for a journal, rules are applied in sequence order.
The first returning results is kept.