class LedgerError(Exception):
    """Base class for errors that should be translated into 4xx API responses."""


class AccountNotFound(LedgerError):
    pass


class AccountFrozen(LedgerError):
    pass


class CurrencyMismatch(LedgerError):
    pass


class InsufficientFunds(LedgerError):
    pass


class TransactionNotFound(LedgerError):
    pass


class TransactionNotPendingApproval(LedgerError):
    pass
