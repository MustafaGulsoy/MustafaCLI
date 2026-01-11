"""
Rate Limiting - Request Rate Control
=====================================

Rate limiting for API calls and tool execution.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict

from .logging_config import get_logger
from .exceptions import ModelRateLimitError

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    calls_per_period: int = 100  # Number of calls allowed
    period_seconds: int = 60  # Time period in seconds
    burst_size: int = 10  # Burst allowance


class RateLimiter:
    """
    Token bucket rate limiter.

    Features:
    - Token bucket algorithm
    - Burst handling
    - Multiple resource tracking
    - Auto-reset

    Example:
        limiter = RateLimiter(calls_per_period=100, period_seconds=60)

        # Check and consume
        await limiter.acquire("api_calls")

        # Or check without consuming
        if limiter.check("api_calls"):
            # Do work
            limiter.consume("api_calls")
    """

    def __init__(
        self,
        calls_per_period: int = 100,
        period_seconds: int = 60,
        burst_size: Optional[int] = None,
    ):
        self.calls_per_period = calls_per_period
        self.period_seconds = period_seconds
        self.burst_size = burst_size or (calls_per_period // 10)

        # Token bucket
        self._tokens = calls_per_period
        self._last_refill = time.time()
        self._lock = asyncio.Lock()

        # Statistics
        self._total_requests = 0
        self._rejected_requests = 0

        logger.info(
            "rate_limiter_initialized",
            calls_per_period=calls_per_period,
            period_seconds=period_seconds,
            burst_size=self.burst_size,
        )

    def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_refill

        # Calculate tokens to add
        tokens_to_add = (elapsed / self.period_seconds) * self.calls_per_period
        self._tokens = min(self._tokens + tokens_to_add, self.calls_per_period)
        self._last_refill = now

    async def acquire(self, resource: str = "default", tokens: int = 1) -> None:
        """
        Acquire tokens, waiting if necessary.

        Args:
            resource: Resource identifier (for tracking)
            tokens: Number of tokens to acquire

        Raises:
            ModelRateLimitError: If rate limit exceeded and no retry possible
        """
        async with self._lock:
            self._refill_tokens()
            self._total_requests += 1

            if self._tokens >= tokens:
                # Tokens available
                self._tokens -= tokens
                logger.debug(
                    "rate_limit_acquired",
                    resource=resource,
                    tokens=tokens,
                    remaining=self._tokens,
                )
                return

            # Not enough tokens - calculate wait time
            wait_time = (tokens - self._tokens) / (
                self.calls_per_period / self.period_seconds
            )

            logger.warning(
                "rate_limit_waiting",
                resource=resource,
                wait_seconds=wait_time,
                remaining_tokens=self._tokens,
            )

            # Wait for tokens
            await asyncio.sleep(wait_time)

            # Try again after waiting
            self._refill_tokens()
            if self._tokens >= tokens:
                self._tokens -= tokens
                logger.debug(
                    "rate_limit_acquired_after_wait",
                    resource=resource,
                    tokens=tokens,
                    remaining=self._tokens,
                )
            else:
                # Still not enough (shouldn't happen)
                self._rejected_requests += 1
                raise ModelRateLimitError(
                    message=f"Rate limit exceeded for {resource}",
                    retry_after=int(wait_time),
                )

    def check(self, tokens: int = 1) -> bool:
        """Check if tokens are available without consuming."""
        self._refill_tokens()
        return self._tokens >= tokens

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens without waiting.

        Returns:
            True if tokens consumed, False if not available
        """
        self._refill_tokens()

        if self._tokens >= tokens:
            self._tokens -= tokens
            self._total_requests += 1
            return True

        self._rejected_requests += 1
        return False

    def get_stats(self) -> Dict:
        """Get rate limiter statistics."""
        self._refill_tokens()
        return {
            "total_requests": self._total_requests,
            "rejected_requests": self._rejected_requests,
            "current_tokens": self._tokens,
            "max_tokens": self.calls_per_period,
            "utilization": 1 - (self._tokens / self.calls_per_period),
        }

    def reset(self) -> None:
        """Reset rate limiter."""
        self._tokens = self.calls_per_period
        self._last_refill = time.time()
        self._total_requests = 0
        self._rejected_requests = 0
        logger.info("rate_limiter_reset")


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter.

    More accurate than token bucket for strict rate limiting.

    Example:
        limiter = SlidingWindowRateLimiter(calls_per_period=100, period_seconds=60)

        if await limiter.allow("api_calls"):
            # Make API call
            pass
    """

    def __init__(self, calls_per_period: int = 100, period_seconds: int = 60):
        self.calls_per_period = calls_per_period
        self.period_seconds = period_seconds
        self._requests: deque = deque()
        self._lock = asyncio.Lock()

        logger.info(
            "sliding_window_limiter_initialized",
            calls_per_period=calls_per_period,
            period_seconds=period_seconds,
        )

    def _clean_old_requests(self) -> None:
        """Remove requests outside the window."""
        now = time.time()
        cutoff = now - self.period_seconds

        while self._requests and self._requests[0] < cutoff:
            self._requests.popleft()

    async def allow(self, resource: str = "default") -> bool:
        """
        Check if request is allowed.

        Returns:
            True if allowed, False if rate limited
        """
        async with self._lock:
            self._clean_old_requests()

            if len(self._requests) < self.calls_per_period:
                # Allow request
                self._requests.append(time.time())
                logger.debug(
                    "rate_limit_allowed",
                    resource=resource,
                    count=len(self._requests),
                    limit=self.calls_per_period,
                )
                return True

            # Rate limited
            logger.warning(
                "rate_limit_exceeded",
                resource=resource,
                count=len(self._requests),
                limit=self.calls_per_period,
            )
            return False

    def get_remaining(self) -> int:
        """Get remaining calls in current window."""
        self._clean_old_requests()
        return max(0, self.calls_per_period - len(self._requests))

    def get_reset_time(self) -> Optional[datetime]:
        """Get time when oldest request expires."""
        if self._requests:
            oldest = self._requests[0]
            reset_time = oldest + self.period_seconds
            return datetime.fromtimestamp(reset_time)
        return None

    def reset(self) -> None:
        """Reset rate limiter."""
        self._requests.clear()
        logger.info("sliding_window_limiter_reset")


class PerResourceRateLimiter:
    """
    Rate limiter with per-resource tracking.

    Allows different rate limits for different resources.

    Example:
        limiter = PerResourceRateLimiter()
        limiter.set_limit("api_calls", calls_per_period=1000, period_seconds=60)
        limiter.set_limit("tool_calls", calls_per_period=100, period_seconds=60)

        await limiter.acquire("api_calls")
        await limiter.acquire("tool_calls")
    """

    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
        self._lock = asyncio.Lock()

    def set_limit(
        self,
        resource: str,
        calls_per_period: int,
        period_seconds: int,
        burst_size: Optional[int] = None,
    ) -> None:
        """Set rate limit for a resource."""
        self._limiters[resource] = RateLimiter(
            calls_per_period=calls_per_period,
            period_seconds=period_seconds,
            burst_size=burst_size,
        )
        logger.info(
            "resource_limit_set",
            resource=resource,
            calls_per_period=calls_per_period,
            period_seconds=period_seconds,
        )

    async def acquire(self, resource: str, tokens: int = 1) -> None:
        """Acquire tokens for resource."""
        if resource not in self._limiters:
            # No limit set for this resource
            return

        await self._limiters[resource].acquire(resource, tokens)

    def check(self, resource: str, tokens: int = 1) -> bool:
        """Check if tokens available for resource."""
        if resource not in self._limiters:
            return True
        return self._limiters[resource].check(tokens)

    def get_stats(self, resource: Optional[str] = None) -> Dict:
        """Get statistics for resource(s)."""
        if resource:
            if resource in self._limiters:
                return {resource: self._limiters[resource].get_stats()}
            return {}

        # All resources
        return {
            name: limiter.get_stats()
            for name, limiter in self._limiters.items()
        }

    def reset(self, resource: Optional[str] = None) -> None:
        """Reset rate limiter(s)."""
        if resource:
            if resource in self._limiters:
                self._limiters[resource].reset()
        else:
            for limiter in self._limiters.values():
                limiter.reset()
