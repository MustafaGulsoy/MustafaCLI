"""
Tests for Rate Limiting
========================

Tests for rate limiting system.
"""

import pytest
import asyncio
import time

from src.core.rate_limit import (
    RateLimiter,
    SlidingWindowRateLimiter,
    PerResourceRateLimiter,
)
from src.core.exceptions import ModelRateLimitError


class TestRateLimiter:
    """Tests for RateLimiter."""

    @pytest.mark.asyncio
    async def test_allow_within_limit(self):
        """Test requests within limit are allowed."""
        limiter = RateLimiter(calls_per_period=10, period_seconds=1)

        # Should allow 10 calls
        for _ in range(10):
            await limiter.acquire()

        stats = limiter.get_stats()
        assert stats["total_requests"] == 10
        assert stats["rejected_requests"] == 0

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self):
        """Test rate limiting when exceeded."""
        limiter = RateLimiter(calls_per_period=5, period_seconds=10)

        # Consume all tokens
        for _ in range(5):
            await limiter.acquire()

        # Check remaining
        assert not limiter.check()

    @pytest.mark.asyncio
    async def test_token_refill(self):
        """Test token refilling over time."""
        limiter = RateLimiter(calls_per_period=10, period_seconds=1)

        # Consume some tokens
        for _ in range(5):
            await limiter.acquire()

        # Wait for refill
        await asyncio.sleep(0.6)  # 60% of period = 6 tokens

        # Should have tokens now
        assert limiter.check(tokens=5)

    @pytest.mark.asyncio
    async def test_burst_handling(self):
        """Test burst request handling."""
        limiter = RateLimiter(calls_per_period=10, period_seconds=1, burst_size=5)

        # Burst of requests should be allowed up to burst_size
        for _ in range(10):
            await limiter.acquire()

        stats = limiter.get_stats()
        assert stats["total_requests"] == 10


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter."""

    @pytest.mark.asyncio
    async def test_allow_within_window(self):
        """Test requests within window are allowed."""
        limiter = SlidingWindowRateLimiter(calls_per_period=5, period_seconds=1)

        # Should allow 5 calls
        for _ in range(5):
            assert await limiter.allow()

        # 6th call should be rejected
        assert not await limiter.allow()

    @pytest.mark.asyncio
    async def test_window_sliding(self):
        """Test window slides over time."""
        limiter = SlidingWindowRateLimiter(calls_per_period=5, period_seconds=1)

        # Fill window
        for _ in range(5):
            await limiter.allow()

        # Wait for window to slide
        await asyncio.sleep(1.1)

        # Should allow again
        assert await limiter.allow()

    @pytest.mark.asyncio
    async def test_get_remaining(self):
        """Test getting remaining calls."""
        limiter = SlidingWindowRateLimiter(calls_per_period=10, period_seconds=1)

        # Make some calls
        for _ in range(3):
            await limiter.allow()

        remaining = limiter.get_remaining()
        assert remaining == 7

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test resetting rate limiter."""
        limiter = SlidingWindowRateLimiter(calls_per_period=5, period_seconds=1)

        # Fill window
        for _ in range(5):
            await limiter.allow()

        # Reset
        limiter.reset()

        # Should allow again
        assert await limiter.allow()


class TestPerResourceRateLimiter:
    """Tests for PerResourceRateLimiter."""

    @pytest.mark.asyncio
    async def test_per_resource_limits(self):
        """Test different limits for different resources."""
        limiter = PerResourceRateLimiter()

        limiter.set_limit("api_calls", calls_per_period=10, period_seconds=1)
        limiter.set_limit("tool_calls", calls_per_period=5, period_seconds=1)

        # API calls
        for _ in range(10):
            await limiter.acquire("api_calls")

        # Tool calls
        for _ in range(5):
            await limiter.acquire("tool_calls")

        # Check limits
        assert not limiter.check("api_calls")
        assert not limiter.check("tool_calls")

    @pytest.mark.asyncio
    async def test_no_limit_for_undefined_resource(self):
        """Test unlimited for undefined resources."""
        limiter = PerResourceRateLimiter()

        # Should allow unlimited for undefined resource
        for _ in range(100):
            await limiter.acquire("undefined_resource")

        assert limiter.check("undefined_resource")

    @pytest.mark.asyncio
    async def test_get_stats_all(self):
        """Test getting stats for all resources."""
        limiter = PerResourceRateLimiter()

        limiter.set_limit("res1", calls_per_period=10, period_seconds=1)
        limiter.set_limit("res2", calls_per_period=20, period_seconds=1)

        await limiter.acquire("res1")
        await limiter.acquire("res2")

        stats = limiter.get_stats()
        assert "res1" in stats
        assert "res2" in stats

    @pytest.mark.asyncio
    async def test_reset_specific_resource(self):
        """Test resetting specific resource."""
        limiter = PerResourceRateLimiter()

        limiter.set_limit("res1", calls_per_period=2, period_seconds=1)
        limiter.set_limit("res2", calls_per_period=2, period_seconds=1)

        # Fill both
        await limiter.acquire("res1")
        await limiter.acquire("res1")
        await limiter.acquire("res2")
        await limiter.acquire("res2")

        # Reset only res1
        limiter.reset("res1")

        # res1 should work, res2 shouldn't
        assert limiter.check("res1")
        assert not limiter.check("res2")
