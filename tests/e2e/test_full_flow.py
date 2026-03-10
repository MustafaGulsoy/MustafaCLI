"""E2E tests for full application flow."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
class TestFullFlow:
    async def test_root_endpoint(self, client):
        """Root endpoint should return API info."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "MustafaCLI API"
        assert "version" in data

    async def test_health_check(self, client):
        """Health check should return system status."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "ollama_connected" in data
        assert "active_sessions" in data

    async def test_api_versioning(self, client, auth_headers):
        """API v1 endpoints should be accessible."""
        resp = await client.get("/api/v1/sessions", headers=auth_headers)
        assert resp.status_code == 200

    async def test_session_lifecycle(self, client, auth_headers):
        """Create, get, list, and delete a session."""
        # Create session
        resp = await client.post(
            "/api/v1/sessions?working_dir=.&enable_rag=false",
            headers=auth_headers,
        )
        assert resp.status_code == 201
        session = resp.json()
        session_id = session["session_id"]
        assert session["active"] is True

        # Get session
        resp = await client.get(
            f"/api/v1/sessions/{session_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == session_id

        # List sessions
        resp = await client.get("/api/v1/sessions", headers=auth_headers)
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) >= 1

        # Delete session
        resp = await client.delete(
            f"/api/v1/sessions/{session_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    async def test_session_not_found(self, client, auth_headers):
        """Non-existent session returns 404."""
        resp = await client.get(
            "/api/v1/sessions/nonexistent-id",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_models_serialization(self, client):
        """API models should serialize correctly."""
        from src.api.models import (
            ChatResponse,
            ErrorResponse,
            HealthResponse,
            SessionInfo,
        )
        from datetime import datetime

        health = HealthResponse(
            status="healthy",
            ollama_connected=True,
            rag_available=False,
            active_sessions=0,
            timestamp=datetime.now(),
        )
        assert health.model_dump()["status"] == "healthy"

        session = SessionInfo(
            session_id="test",
            created_at=datetime.now(),
            working_dir=".",
            rag_enabled=False,
            active=True,
        )
        assert session.model_dump()["session_id"] == "test"
