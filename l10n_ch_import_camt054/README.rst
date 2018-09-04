.. image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
    :alt: License: AGPL-3

Switzerland camt 054 and transfert account reconcile
====================================================

This module allow you to import camt 054 and reconcile all lines in the transfert account.

** Features list :**
    * import camt 054
    * refuse the import of a camt 054 file when the NtryRef field is different from the original camt 054
    * Add children in school to employee
    * New function to reconcile automatically all the lines from the transfert account

** Remarks :**
To use the reconcilion function you need to make a cron. You can do it in the menu : ```Settings->Automation->Scheduled Actions```
and create a new action. The object needed to reach the new function is : ```account.bank.statement.line``` and the function name is : ```camt054_reconcile```.
The unique parameter is the transfert account number, for example : ```("1099",)```

Known issues / Roadmap
======================

Contributors
------------

* Marco Monzione
