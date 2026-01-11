"""
Tests for Context Management
=============================

Tests for context window management and compaction.
"""

import pytest
from datetime import datetime

from src.core.context import (
    ContextManager,
    Message,
    MessageRole,
    TokenEstimator,
)


class TestTokenEstimator:
    """Tests for TokenEstimator."""

    def test_estimate_text(self):
        """Test token estimation for text."""
        estimator = TokenEstimator(chars_per_token=4.0)
        tokens = estimator.estimate("hello world")  # 11 chars
        assert tokens == 2  # 11 / 4 = 2.75 -> 2

    def test_estimate_message(self):
        """Test token estimation for messages."""
        estimator = TokenEstimator()
        message = Message(
            role=MessageRole.USER,
            content="test message",
            timestamp=datetime.now(),
        )
        tokens = estimator.estimate_message(message)
        assert tokens > 0


class TestContextManager:
    """Tests for ContextManager."""

    def test_add_message(self):
        """Test adding messages."""
        ctx = ContextManager(max_tokens=1000, reserve_tokens=100)
        message = Message(
            role=MessageRole.USER,
            content="test",
            timestamp=datetime.now(),
        )
        ctx.add_message(message)
        assert len(ctx.messages) == 1

    def test_should_compact(self):
        """Test compaction threshold."""
        ctx = ContextManager(max_tokens=100, reserve_tokens=10)

        # Add messages until threshold
        for i in range(20):
            message = Message(
                role=MessageRole.USER,
                content="x" * 20,  # 20 chars ~= 5 tokens each
                timestamp=datetime.now(),
            )
            ctx.add_message(message)

        # Should trigger compaction
        assert ctx.should_compact(threshold=0.8)

    def test_get_recent_messages(self):
        """Test retrieving recent messages."""
        ctx = ContextManager()

        for i in range(10):
            ctx.add_message(Message(
                role=MessageRole.USER,
                content=f"message {i}",
                timestamp=datetime.now(),
            ))

        recent = ctx.get_recent_messages(5)
        assert len(recent) == 5
        assert "message 9" in recent[-1].content

    def test_clear(self):
        """Test clearing context."""
        ctx = ContextManager()
        ctx.add_message(Message(
            role=MessageRole.USER,
            content="test",
            timestamp=datetime.now(),
        ))

        ctx.clear()
        assert len(ctx.messages) == 0
        assert ctx._total_tokens == 0
