import time
from typing import Literal


CircuitState = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    def __init__(
        self,
        fail_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.fail_threshold = fail_threshold
        self.recovery_timeout = recovery_timeout
        self.state: CircuitState = "closed"
        self.fail_count = 0
        self.last_fail_time = 0.0

    def is_available(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.monotonic() - self.last_fail_time > self.recovery_timeout:
                self.state = "half_open"
                return True
            return False
        return True

    def record_success(self) -> None:
        self.fail_count = 0
        self.state = "closed"

    def record_failure(self) -> None:
        self.fail_count += 1
        self.last_fail_time = time.monotonic()
        if self.fail_count >= self.fail_threshold:
            self.state = "open"


CIRCUIT_BREAKERS: dict[str, CircuitBreaker] = {}


def get_breaker(key: str) -> CircuitBreaker:
    if key not in CIRCUIT_BREAKERS:
        CIRCUIT_BREAKERS[key] = CircuitBreaker()
    return CIRCUIT_BREAKERS[key]
