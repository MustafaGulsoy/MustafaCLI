"""Tests for API v1 endpoints."""
from __future__ import annotations

import pytest

from src.api.models import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    PluginInfo,
    SessionInfo,
    TokenResponse,
    UserInfo,
)


class TestApiModels:
    def test_chat_request(self):
        req = ChatRequest(session_id="abc", message="hello")
        assert req.session_id == "abc"
        assert req.message == "hello"

    def test_chat_response(self):
        resp = ChatResponse(content="hi", state="completed", iteration=1)
        assert resp.content == "hi"
        assert resp.tool_calls == []

    def test_health_response(self):
        from datetime import datetime

        resp = HealthResponse(
            status="healthy",
            ollama_connected=True,
            rag_available=False,
            active_sessions=2,
            timestamp=datetime.now(),
        )
        assert resp.status == "healthy"
        assert resp.active_sessions == 2

    def test_token_response(self):
        resp = TokenResponse(
            access_token="abc", refresh_token="def", token_type="bearer"
        )
        assert resp.token_type == "bearer"

    def test_user_info(self):
        user = UserInfo(
            id=1,
            username="test",
            email="test@test.com",
            is_active=True,
            is_admin=False,
        )
        assert user.username == "test"

    def test_plugin_info(self):
        plugin = PluginInfo(
            name="test-plugin",
            version="1.0.0",
            description="Test",
            plugin_type="entry_point",
            enabled=True,
        )
        assert plugin.name == "test-plugin"

    def test_error_response(self):
        err = ErrorResponse(detail="Not found", error_code="NOT_FOUND")
        assert err.detail == "Not found"
        assert err.error_code == "NOT_FOUND"
