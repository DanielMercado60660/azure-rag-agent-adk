"""
Circuit breaker pattern for tool resilience
Implements ADK best practice for fault tolerance in tool execution
"""
import logging
import time
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class BreakerState:
    """
    Circuit breaker state for a single tool.

    States:
    - closed: Normal operation, requests allowed
    - open: Tool failing, requests blocked
    - half_open: Testing if tool recovered
    """
    failure_rate: float = 0.0
    opened_at: float = 0.0
    state: str = "closed"  # closed | open | half_open
    consecutive_failures: int = 0


class CircuitBreaker:
    """
    Circuit breaker for tool failure protection.

    ADK Best Practice: Implement circuit breakers to prevent cascading
    failures when tools become unavailable in multi-agent workflows.

    Pattern:
    1. Monitor tool failure rates using exponential moving average
    2. Open circuit when failure threshold exceeded
    3. Enter half-open state after timeout to test recovery
    4. Close circuit on successful execution
    """

    def __init__(self, threshold: float = 0.5, timeout: float = 30.0):
        """
        Initialize circuit breaker.

        Args:
            threshold: Failure rate threshold to open circuit (0.0-1.0)
            timeout: Seconds to wait before testing recovery
        """
        self.threshold = threshold
        self.timeout = timeout
        self._tools: Dict[str, BreakerState] = {}
        self._alpha = 0.2  # EMA smoothing factor

    def is_closed(self, tool_name: str) -> bool:
        """
        Check if circuit is closed (tool can execute).

        ADK Best Practice: Check circuit state before tool execution
        to fail fast and prevent wasted resources.
        """
        breaker = self._tools.get(tool_name, BreakerState())

        # Transition from open to half-open after timeout
        if breaker.state == "open":
            if (time.time() - breaker.opened_at) > self.timeout:
                breaker.state = "half_open"
                logger.info(f"Circuit {tool_name} half-open (testing recovery)")

        return breaker.state in ("closed", "half_open")

    def record_success(self, tool_name: str):
        """
        Record successful tool execution.

        ADK Best Practice: Track successes to enable automatic recovery
        and maintain failure rate metrics.
        """
        breaker = self._tools.setdefault(tool_name, BreakerState())
        breaker.consecutive_failures = 0

        # Update failure rate with exponential moving average
        breaker.failure_rate = (1 - self._alpha) * breaker.failure_rate

        # Close circuit if half-open and success
        if breaker.state == "half_open":
            breaker.state = "closed"
            logger.info(f"Circuit {tool_name} closed (recovered)")

    def record_failure(self, tool_name: str):
        """
        Record failed tool execution.

        ADK Best Practice: Open circuit proactively to prevent
        repeated failures in agent workflows.
        """
        breaker = self._tools.setdefault(tool_name, BreakerState())
        breaker.consecutive_failures += 1

        # Update failure rate with exponential moving average
        breaker.failure_rate = (1 - self._alpha) * breaker.failure_rate + self._alpha

        # Open circuit if threshold exceeded
        if breaker.failure_rate > self.threshold and breaker.state != "open":
            breaker.state = "open"
            breaker.opened_at = time.time()
            logger.warning(
                f"Circuit {tool_name} opened (failure rate: {breaker.failure_rate:.2f})"
            )


# Global circuit breaker instance
circuit_breaker = CircuitBreaker()
