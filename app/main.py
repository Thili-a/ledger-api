from fastapi import FastAPI

from app.api import accounts, auth, transfers
from app.db.base import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Ikano-style Ledger API",
    description="Double-entry ledger and payments API built as a portfolio project "
    "demonstrating Python backend patterns relevant to banking systems: "
    "idempotent transfers, RBAC, and event-driven notifications.",
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transfers.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
