# Overview

The off-balance feature in Compassion Accounting is designed to handle specific accounting requirements where certain accounts need to be managed off the main balance sheet. This is particularly useful for handling donations, sponsorships, or other transactions that should not directly impact the company's financial statements until they are fully realized.

# Why Use Off-Balance Accounts?

In some accounting scenarios, it is necessary to track certain transactions separately from the main financial statements. Off-balance accounts allow for this separation, ensuring that these transactions are recorded and managed without affecting the overall financial health indicators of the company.

# Process

## 1. Identifying Off-Balance Accounts

During the reconciliation process, the system identifies accounts that are marked as off-balance. These accounts are typically used for specific transactions, such as sponsorships or donations, where the actual cash flow may not align with the recognition of income. The `off_balance_asset_account_id` field in the `res.company` model is used to configure the off-balance asset account.

## 2. Reconciliation

During the reconciliation process, the system checks if any account move lines (AMLs) correspond to off-balance receivable accounts. If so, it adds additional account move lines to comply with the Nordic offset balance specification. This involves prorating the amounts based on the payment made and the value of each product line. The system uses the `on_balance_account_id` field to determine the linked on-balance account for each off-balance account.

## 3. Example

Here is an example of how the off-balance feature works:

- A payment is made involving an off-balance receivable account.
- The system identifies the off-balance accounts and calculates the prorated amounts for each product line.
- Additional account move lines are created to reflect the off-balance transactions.
- The reconciliation process ensures that the off-balance entries are properly managed.

# Purpose

The stock off-balance feature cannot be used because:

- It does not support reconcilable off-balance accounts. Instead, the system uses 9xxx accounts and a configuration to define:
  - **Receivable (off-balance)**: A
  - **Asset (off-balance)**: B

This functionality adds the following entries to the payment move if there is an off-balance receivable account (A):

1. The off-balance asset account (B).
2. The outstanding account again.

This ensures compliance with the Nordic offset balance specification and proper management of off-balance transactions.
