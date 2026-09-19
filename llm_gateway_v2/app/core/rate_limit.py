import time

from fastapi import Depends, Header

from app.core.errors import GatewayError


class TokenBucket:
    def __init__(self, capacity: int = 60, refill_rate: float = 10.0) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


class RateLimiter:
    def __init__(self) -> None:
        self.buckets: dict[str, TokenBucket] = {}

    async def check(self, token: str) -> bool:
        if token not in self.buckets:
            self.buckets[token] = TokenBucket()
        return self.buckets[token].consume()


rate_limiter = RateLimiter()


async def rate_limit(
    authorization: str | None = Header(default=None),
) -> None:
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")

    if not await rate_limiter.check(token):
        raise GatewayError("rate_limited", "Rate limit exceeded", status_code=429)


rate_limit_dependency = Depends(rate_limit)
