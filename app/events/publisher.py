from functools import lru_cache
from typing import Protocol

import redis

from app.core.config import settings

TRANSFER_COMPLETED_STREAM = "transfers.completed"


class EventPublisher(Protocol):
    def publish_transfer_completed(self, transaction_id: str) -> None: ...


class RedisEventPublisher:
    """Publishes to a Redis Stream so a separate worker process (app/worker.py)
    can react to settled transfers without blocking the request/response path."""

    def __init__(self, redis_url: str = settings.redis_url) -> None:
        self._client = redis.from_url(redis_url)

    def publish_transfer_completed(self, transaction_id: str) -> None:
        self._client.xadd(TRANSFER_COMPLETED_STREAM, {"transaction_id": transaction_id})


class NullEventPublisher:
    """No-op publisher used in tests and local runs without Redis available."""

    def __init__(self) -> None:
        self.published: list[str] = []

    def publish_transfer_completed(self, transaction_id: str) -> None:
        self.published.append(transaction_id)


@lru_cache
def get_event_publisher() -> EventPublisher:
    try:
        publisher = RedisEventPublisher()
        publisher._client.ping()
        return publisher
    except redis.exceptions.RedisError:
        return NullEventPublisher()
