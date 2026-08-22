import time
import asyncio
import uuid
from typing import Dict, Optional


class TokenBucket:
    """Thread-safe / Async in-memory Token Bucket for queue rate limiting."""

    def __init__(self, rate_limit_rps: float, capacity: Optional[float] = None):
        self.rate_limit_rps = max(1.0, float(rate_limit_rps))
        self.capacity = float(capacity or self.rate_limit_rps)
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def consume(self, tokens: float = 1.0) -> bool:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.last_refill = now

            # Refill tokens according to elapsed time
            self.tokens = min(self.capacity, self.tokens + (elapsed * self.rate_limit_rps))

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


class QueueRateLimiter:
    """Global manager tracking token buckets per queue."""

    _buckets: Dict[uuid.UUID, TokenBucket] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def allow_claim(cls, queue_id: uuid.UUID, rate_limit_rps: Optional[int]) -> bool:
        if not rate_limit_rps or rate_limit_rps <= 0:
            return True  # No rate limit configured

        async with cls._lock:
            if queue_id not in cls._buckets:
                cls._buckets[queue_id] = TokenBucket(rate_limit_rps=rate_limit_rps)
            bucket = cls._buckets[queue_id]

        return await bucket.consume(1.0)
