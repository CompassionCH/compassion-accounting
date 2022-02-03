.. image:: https://img.shields.io/badge/licence-LGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/lpgl
   :alt: License: AGPL-3

==============================
Download Payment return via EBICS
==============================

This module allows to Download a Payment return to odoo via the EBICS protocol.

Installation
============

This module depends upon the following modules (cf. apps.odoo.com):

- account_ebics
- account_payment_return

Usage
=====

create a pain002 file type and after an upload of a payment order download the pain002 return file
if the file tells it's accepted, the payment order will be set as successully uploaded in not already, if the return contain error, it will be process in the payment return module.

Known issues / Roadmap
======================

