"""E2E test configuration and fixtures."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def test_app():
    """Create test FastAPI app with in-memory SQLite."""
    import os

    os.environ["AGENT_DATABASE_URL"] = "sqlite+aiosqlite:///test_e2e.db"

    from src.db.database import close_db, create_tables, init_db

    await init_db("sqlite+aiosqlite:///test_e2e.db")
    await create_tables()

    from src.api.main import app

    yield app

    await close_db()

    # Cleanup test database
    import pathlib

    db_file = pathlib.Path("test_e2e.db")
    if db_file.exists():
        db_file.unlink()


@pytest.fixture
async def client(test_app):
    """Create async HTTP client."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def auth_headers(client):
    """Register a user and return auth headers."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@test.com",
            "password": "testpass123",
        },
    )
    if resp.status_code == 201:
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    # User might already exist, try login
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpass123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
