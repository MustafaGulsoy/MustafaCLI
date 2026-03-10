"""E2E tests for authentication flow."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
class TestAuthFlow:
    async def test_register(self, client):
        """Register a new user."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "new@test.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_duplicate_username(self, client):
        """Cannot register with existing username."""
        payload = {
            "username": "dupuser",
            "email": "dup@test.com",
            "password": "password123",
        }
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 400

    async def test_login(self, client):
        """Login with valid credentials."""
        # Register first
        await client.post(
            "/api/v1/auth/register",
            json={
                "username": "loginuser",
                "email": "login@test.com",
                "password": "password123",
            },
        )
        # Login
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "loginuser", "password": "password123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    async def test_login_invalid(self, client):
        """Login with invalid credentials fails."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent", "password": "wrong"},
        )
        assert resp.status_code == 401

    async def test_refresh_token(self, client):
        """Refresh access token."""
        # Register
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "refreshuser",
                "email": "refresh@test.com",
                "password": "password123",
            },
        )
        refresh_token = resp.json()["refresh_token"]

        # Refresh
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_protected_endpoint_without_token(self, client):
        """Protected endpoints require auth."""
        resp = await client.get("/api/v1/sessions")
        assert resp.status_code in [401, 403]

    async def test_protected_endpoint_with_token(self, client, auth_headers):
        """Protected endpoints work with valid token."""
        resp = await client.get("/api/v1/sessions", headers=auth_headers)
        assert resp.status_code == 200
