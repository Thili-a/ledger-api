from sqlalchemy.orm import Session

from app.core.config import settings
from app.events.publisher import EventPublisher
from app.models.account import Account
from app.models.ledger_entry import EntryType, LedgerEntry
from app.models.transaction import Transaction, TransactionStatus
from app.services.errors import (
    AccountFrozen,
    AccountNotFound,
    CurrencyMismatch,
    InsufficientFunds,
    TransactionNotFound,
    TransactionNotPendingApproval,
)


def _locked_account(db: Session, account_id: str) -> Account:
    account = db.query(Account).filter(Account.id == account_id).with_for_update().one_or_none()
    if account is None:
        raise AccountNotFound(account_id)
    return account


def _apply_double_entry(db: Session, transaction: Transaction, from_account: Account, to_account: Account) -> None:
    from_account.balance_minor -= transaction.amount_minor
    to_account.balance_minor += transaction.amount_minor

    db.add_all(
        [
            LedgerEntry(
                transaction_id=transaction.id,
                account_id=from_account.id,
                entry_type=EntryType.debit,
                amount_minor=transaction.amount_minor,
                balance_after_minor=from_account.balance_minor,
            ),
            LedgerEntry(
                transaction_id=transaction.id,
                account_id=to_account.id,
                entry_type=EntryType.credit,
                amount_minor=transaction.amount_minor,
                balance_after_minor=to_account.balance_minor,
            ),
        ]
    )
    transaction.status = TransactionStatus.completed


def create_transfer(
    db: Session,
    publisher: EventPublisher,
    *,
    idempotency_key: str,
    from_account_id: str,
    to_account_id: str,
    amount_minor: int,
    currency: str,
) -> Transaction:
    """Creates (or replays) a transfer between two accounts.

    Idempotency: a retried request with the same idempotency_key returns the
    original Transaction instead of moving money twice — safe for clients that
    retry on timeouts.

    Large transfers (>= settings.large_transfer_approval_threshold) are parked
    as pending_approval instead of settled immediately, mirroring a real
    maker-checker control; see approve_transfer for the second step.
    """
    existing = db.query(Transaction).filter(Transaction.idempotency_key == idempotency_key).one_or_none()
    if existing is not None:
        return existing

    from_account = _locked_account(db, from_account_id)
    to_account = _locked_account(db, to_account_id)

    if from_account.currency != currency or to_account.currency != currency:
        raise CurrencyMismatch(f"expected {currency}")
    if from_account.is_frozen or to_account.is_frozen:
        raise AccountFrozen(from_account_id if from_account.is_frozen else to_account_id)

    if amount_minor >= settings.large_transfer_approval_threshold:
        transaction = Transaction(
            idempotency_key=idempotency_key,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount_minor=amount_minor,
            currency=currency,
            status=TransactionStatus.pending_approval,
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        return transaction

    if from_account.balance_minor < amount_minor:
        transaction = Transaction(
            idempotency_key=idempotency_key,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount_minor=amount_minor,
            currency=currency,
            status=TransactionStatus.failed,
            failure_reason="insufficient_funds",
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        raise InsufficientFunds(from_account_id)

    transaction = Transaction(
        idempotency_key=idempotency_key,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount_minor=amount_minor,
        currency=currency,
    )
    db.add(transaction)
    db.flush()

    _apply_double_entry(db, transaction, from_account, to_account)
    db.commit()
    db.refresh(transaction)

    publisher.publish_transfer_completed(transaction.id)
    return transaction


def approve_transfer(db: Session, publisher: EventPublisher, transaction_id: str) -> Transaction:
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).one_or_none()
    if transaction is None:
        raise TransactionNotFound(transaction_id)
    if transaction.status != TransactionStatus.pending_approval:
        raise TransactionNotPendingApproval(transaction_id)

    from_account = _locked_account(db, transaction.from_account_id)
    to_account = _locked_account(db, transaction.to_account_id)

    if from_account.balance_minor < transaction.amount_minor:
        transaction.status = TransactionStatus.failed
        transaction.failure_reason = "insufficient_funds"
        db.commit()
        db.refresh(transaction)
        raise InsufficientFunds(from_account.id)

    _apply_double_entry(db, transaction, from_account, to_account)
    db.commit()
    db.refresh(transaction)

    publisher.publish_transfer_completed(transaction.id)
    return transaction
