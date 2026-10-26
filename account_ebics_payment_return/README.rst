.. image:: https://img.shields.io/badge/licence-LGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/lpgl
   :alt: License: LGPL-3

==========================================================
Process Payment Order status reports downloaded via EBICS
==========================================================

After a payment order is uploaded, the bank answers with a payment status report
(pain.002). This module applies the report to the payment order it answers when the
EBICS file is processed:

- order rejected: the payment order is cancelled and the reason of the bank is
  posted on it;
- order accepted: the payment order is set as uploaded if not already;
- transactions rejected: each rejected payment is cancelled and its payment lines
  are freed from the order, so that the invoices can be paid again. The reason of
  the bank is posted on the order and on the invoices.

The result is written in the process notes of the EBICS file.

Installation
============

This module depends upon the following modules:

- account_ebics
- account_payment_line_free

Usage
=====

Set the download process method of the pain.002 EBICS file format to ``pain.002``.
The files are processed with the other EBICS files, by the batch import or with the
Process button.

Known issues / Roadmap
======================

- A rejection given only at the payment information level (PmtInfSts) and not per
  transaction is not handled.
- A payment whose invoice is already paid cannot be freed: this is written in the
  process notes and on the payment order.
