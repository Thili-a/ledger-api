# ledger-api

A double-entry ledger and payments API for a fictional bank, built as a focused
portfolio project — not a toy CRUD demo. It exists to show working Python
backend patterns for the parts of a banking system that are easy to get wrong:
money movement, idempotency, and access control.

Companion project: [`../ops-console`](../ops-console) is a separate FastAPI +
HTMX service that talks to this API over REST to give support staff a UI for
account search, freezing, and approving large transfers.

## What it demonstrates

- **Double-entry ledger** — every completed transfer writes exactly one debit
  and one credit `LedgerEntry`, so the ledger always nets to zero and every
  account balance is independently reconstructable from its entries
  (`app/services/ledger.py`).
- **Idempotent writes** — `POST /transfers` requires an `Idempotency-Key`
  header; a retried request with the same key returns the original
  transaction instead of moving money twice.
- **A maker-checker control** — transfers at or above
  `LARGE_TRANSFER_APPROVAL_THRESHOLD` are parked as `pending_approval` instead
  of settling immediately, and require a support/admin user to call
  `POST /transfers/{id}/approve`.
- **RBAC** — three roles (`customer`, `support`, `admin`); customers can only
  see their own accounts, support/admin can search all accounts, freeze them,
  and approve pending transfers.
- **Event-driven side effects** — a completed transfer publishes to a Redis
  Stream (`app/events/publisher.py`); a separate worker process
  (`app/worker.py`) consumes it via a consumer group and writes a
  `Notification` row, independent of and non-blocking for the request path.
- **SQL / data modeling** — SQLAlchemy models with real foreign keys and a
  hand-written Alembic migration (`alembic/versions/0001_initial_schema.py`).
- **Tests that exercise the actual business rules**, not just HTTP shapes —
  see `tests/test_transfers.py` for insufficient-funds, frozen-account,
  idempotency-replay, and approval-threshold cases.

## Design decisions & tradeoffs

- **Cached balance, ledger as source of truth.** `Account.balance_minor` is
  updated transactionally alongside its `LedgerEntry` rows rather than
  computed with `SUM()` on every read. This keeps balance reads O(1), at the
  cost of needing the write path to be correct — which is exactly what the
  idempotency key and row locking (`with_for_update`) in `ledger.py` protect.
- **SQLite in tests, Postgres in prod.** Tests run against an in-memory
  SQLite DB for speed and zero setup; the same SQLAlchemy models run against
  Postgres via `DATABASE_URL`. The tradeoff: SQLite doesn't enforce row
  locking the way Postgres does, so the concurrency guarantees from
  `with_for_update()` are only really tested against Postgres, not in CI.
  A production hardening pass would add a docker-compose-based integration
  test job against real Postgres.
- **`Base.metadata.create_all()` at startup, alongside Alembic.** Convenient
  for local dev with SQLite; Alembic migrations are the real mechanism for
  evolving the Postgres schema. `create_all()` is a no-op against
  already-existing tables so the two don't conflict.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # defaults to sqlite:///./dev.db, no Redis required
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for interactive OpenAPI docs (the "Authorize"
button works with `/auth/login`, since it's a standard OAuth2 password-grant
form).

### With Postgres + Redis + the worker (docker-compose)

From the repo root (`../`):

```bash
docker compose up --build
```

This starts Postgres, Redis, `ledger-api` on :8000, `ledger-worker`, and
`ops-console` on :8080.

## Tests

```bash
pytest -q      # 15 tests, no external services required
ruff check app tests
```

## AWS

See [`deploy/aws`](deploy/aws) — a Terraform skeleton (ECS Fargate + RDS
Postgres + ElastiCache Redis) written to be reviewed, deliberately not
applied against a real account. See that folder's README for what's
included vs. what a production rollout would still need.
