"""Standalone worker process: consumes the 'transfers.completed' Redis Stream
and writes a Notification row per settled transfer, decoupling settlement from
downstream side effects (in a real system: emails, webhooks, fraud checks).

Run with:  python -m app.worker
"""

import logging

import redis

from app.core.config import settings
from app.db.base import SessionLocal
from app.events.publisher import TRANSFER_COMPLETED_STREAM
from app.models.notification import Notification
from app.models.transaction import Transaction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

CONSUMER_GROUP = "ledger-worker"
CONSUMER_NAME = "worker-1"


def _ensure_group(client: redis.Redis) -> None:
    try:
        client.xgroup_create(TRANSFER_COMPLETED_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _handle_event(transaction_id: str) -> None:
    db = SessionLocal()
    try:
        transaction = db.query(Transaction).filter(Transaction.id == transaction_id).one_or_none()
        if transaction is None:
            logger.warning("transaction %s not found, skipping", transaction_id)
            return
        db.add(
            Notification(
                transaction_id=transaction.id,
                message=(
                    f"Transfer {transaction.id} of {transaction.amount_minor} "
                    f"{transaction.currency} settled."
                ),
            )
        )
        db.commit()
        logger.info("notification written for transaction %s", transaction_id)
    finally:
        db.close()


def run() -> None:
    client = redis.from_url(settings.redis_url)
    _ensure_group(client)
    logger.info("worker listening on stream '%s'", TRANSFER_COMPLETED_STREAM)
    while True:
        response = client.xreadgroup(CONSUMER_GROUP, CONSUMER_NAME, {TRANSFER_COMPLETED_STREAM: ">"}, block=5000, count=10)
        for _stream, messages in response or []:
            for message_id, fields in messages:
                transaction_id = fields[b"transaction_id"].decode()
                _handle_event(transaction_id)
                client.xack(TRANSFER_COMPLETED_STREAM, CONSUMER_GROUP, message_id)


if __name__ == "__main__":
    run()
