from pydantic import BaseModel, Field


class OpenAccountRequest(BaseModel):
    currency: str = "EUR"
    opening_balance_minor: int = Field(default=0, ge=0)


class AccountResponse(BaseModel):
    id: str
    owner_id: str
    currency: str
    balance_minor: int
    is_frozen: bool

    model_config = {"from_attributes": True}
