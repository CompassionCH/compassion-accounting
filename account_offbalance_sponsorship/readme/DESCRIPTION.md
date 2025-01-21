 It's not possible to use the stock off-balance feature because
        it's not possible to have a reconciliable off-balance account. So we use the 9xxx account and a configuration to
        define:
        - receivable (off-balance): A
        - asset (off-balance): B
        this function adds in the payment move if there is an off-balance (A) receivable account:
        - the off-balance asset (B)
        - add the outstanding account again.
