from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.base import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import Role, User
from app.schemas.account import AccountResponse, OpenAccountRequest
from app.schemas.transaction import TransactionResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def open_account(
    body: OpenAccountRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Account:
    account = Account(
        owner_id=user.id,
        currency=body.currency,
        balance_minor=body.opening_balance_minor,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _get_owned_or_staff_account(account_id: str, user: User, db: Session) -> Account:
    account = db.query(Account).filter(Account.id == account_id).one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    if user.role == Role.customer and account.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your account")
    return account


@router.get("", response_model=list[AccountResponse])
def list_accounts(
    q: str | None = None,
    user: User = Depends(require_roles(Role.support, Role.admin)),
    db: Session = Depends(get_db),
) -> list[Account]:
    """Support/admin search across all accounts, by owner email/name substring."""
    query = db.query(Account).join(User, Account.owner_id == User.id)
    if q:
        like = f"%{q}%"
        query = query.filter((User.email.ilike(like)) | (User.full_name.ilike(like)))
    return query.order_by(Account.id).limit(50).all()


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Account:
    return _get_owned_or_staff_account(account_id, user, db)


@router.get("/{account_id}/transactions", response_model=list[TransactionResponse])
def list_account_transactions(
    account_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Transaction]:
    _get_owned_or_staff_account(account_id, user, db)
    return (
        db.query(Transaction)
        .filter((Transaction.from_account_id == account_id) | (Transaction.to_account_id == account_id))
        .order_by(Transaction.created_at.desc())
        .all()
    )


@router.post("/{account_id}/freeze", response_model=AccountResponse)
def freeze_account(
    account_id: str,
    user: User = Depends(require_roles(Role.support, Role.admin)),
    db: Session = Depends(get_db),
) -> Account:
    account = db.query(Account).filter(Account.id == account_id).one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    account.is_frozen = True
    db.commit()
    db.refresh(account)
    return account


@router.post("/{account_id}/unfreeze", response_model=AccountResponse)
def unfreeze_account(
    account_id: str,
    user: User = Depends(require_roles(Role.support, Role.admin)),
    db: Session = Depends(get_db),
) -> Account:
    account = db.query(Account).filter(Account.id == account_id).one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    account.is_frozen = False
    db.commit()
    db.refresh(account)
    return account
