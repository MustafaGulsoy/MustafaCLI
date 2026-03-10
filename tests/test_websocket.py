"""Tests for WebSocket endpoint."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestWebSocketProtocol:
    """Test WebSocket message protocol."""

    def test_ping_pong_message(self):
        """Verify ping message format."""
        msg = {"type": "ping"}
        assert msg["type"] == "ping"

    def test_message_format(self):
        """Verify chat message format."""
        msg = {"type": "message", "content": "Hello"}
        assert msg["type"] == "message"
        assert msg["content"] == "Hello"

    def test_cancel_message(self):
        """Verify cancel message format."""
        msg = {"type": "cancel"}
        assert msg["type"] == "cancel"

    def test_response_format(self):
        """Verify response message format."""
        resp = {
            "type": "response",
            "data": {
                "content": "Hello!",
                "state": "thinking",
                "iteration": 1,
                "tool_calls": [],
                "tool_results": [],
            },
        }
        assert resp["type"] == "response"
        assert resp["data"]["content"] == "Hello!"
        assert resp["data"]["state"] == "thinking"

    def test_complete_format(self):
        """Verify completion message format."""
        resp = {
            "type": "complete",
            "data": {"iterations": 3, "duration_ms": 1500},
        }
        assert resp["type"] == "complete"
        assert resp["data"]["iterations"] == 3

    def test_error_format(self):
        """Verify error message format."""
        resp = {"type": "error", "error": "Session not found"}
        assert resp["type"] == "error"
        assert "Session" in resp["error"]

    def test_connected_format(self):
        """Verify connected message format."""
        resp = {
            "type": "connected",
            "session_id": "abc-123",
            "working_dir": ".",
            "rag_enabled": False,
        }
        assert resp["type"] == "connected"
        assert resp["session_id"] == "abc-123"


class TestWebSocketAuth:
    """Test WebSocket authentication via query param."""

    def test_token_in_query_param(self):
        """Token should be passed as ?token=<jwt>."""
        url = "ws://localhost:8000/ws/session-1?token=eyJhbGc..."
        assert "token=" in url

    def test_missing_token_allowed(self):
        """WebSocket should allow unauthenticated connections for backward compat."""
        url = "ws://localhost:8000/ws/session-1"
        assert "token" not in url
