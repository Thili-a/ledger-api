from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_publisher, require_roles
from app.db.base import get_db
from app.events.publisher import EventPublisher
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import Role, User
from app.schemas.transaction import TransactionResponse, TransferRequest
from app.services import ledger
from app.services.errors import (
    AccountFrozen,
    AccountNotFound,
    CurrencyMismatch,
    InsufficientFunds,
    TransactionNotFound,
    TransactionNotPendingApproval,
)

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(
    body: TransferRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    publisher: EventPublisher = Depends(get_publisher),
) -> Transaction:
    try:
        return ledger.create_transfer(
            db,
            publisher,
            idempotency_key=idempotency_key,
            from_account_id=body.from_account_id,
            to_account_id=body.to_account_id,
            amount_minor=body.amount_minor,
            currency=body.currency,
        )
    except AccountNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Account not found: {exc}") from exc
    except AccountFrozen as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Account frozen: {exc}") from exc
    except CurrencyMismatch as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Currency mismatch: {exc}") from exc
    except InsufficientFunds as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, f"Insufficient funds: {exc}") from exc


@router.get("/pending", response_model=list[TransactionResponse])
def list_pending_transfers(
    user: User = Depends(require_roles(Role.support, Role.admin)),
    db: Session = Depends(get_db),
) -> list[Transaction]:
    return (
        db.query(Transaction)
        .filter(Transaction.status == TransactionStatus.pending_approval)
        .order_by(Transaction.created_at)
        .all()
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transfer(
    transaction_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Transaction:
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).one_or_none()
    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return transaction


@router.post("/{transaction_id}/approve", response_model=TransactionResponse)
def approve_transfer(
    transaction_id: str,
    user: User = Depends(require_roles(Role.support, Role.admin)),
    db: Session = Depends(get_db),
    publisher: EventPublisher = Depends(get_publisher),
) -> Transaction:
    try:
        return ledger.approve_transfer(db, publisher, transaction_id)
    except TransactionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found") from exc
    except TransactionNotPendingApproval as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Transaction is not pending approval") from exc
    except InsufficientFunds as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, f"Insufficient funds: {exc}") from exc
