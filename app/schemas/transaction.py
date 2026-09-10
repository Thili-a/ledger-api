from datetime import datetime

from pydantic import BaseModel, Field

from app.models.transaction import TransactionStatus


class TransferRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount_minor: int = Field(gt=0)
    currency: str = "EUR"


class TransactionResponse(BaseModel):
    id: str
    from_account_id: str
    to_account_id: str
    amount_minor: int
    currency: str
    status: TransactionStatus
    failure_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
