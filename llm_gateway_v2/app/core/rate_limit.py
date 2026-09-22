import os
import time


class TokenBucket:
    def __init__(
        self,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> None:
        # 从环境变量读取，便于用独立进程验证限流行为
        self.capacity = (
            capacity if capacity is not None else int(
                os.getenv("RATE_LIMIT_CAPACITY", "60")
            )
        )
        self.refill_rate = (
            refill_rate
            if refill_rate is not None
            else float(os.getenv("RATE_LIMIT_REFILL_RATE", "10.0"))
        )
        self.tokens = float(self.capacity)
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
        # 按 model 分桶，每个模型一个独立 TokenBucket，互不影响
        self.buckets: dict[str, TokenBucket] = {}

    async def check(self, model: str) -> bool:
        if model not in self.buckets:
            self.buckets[model] = TokenBucket()
        return self.buckets[model].consume()


rate_limiter = RateLimiter()
