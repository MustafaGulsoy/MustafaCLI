"""Tests for Neo4j client wrapper."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.plugins.sat_maestro.config import SatMaestroConfig
from src.plugins.sat_maestro.core.neo4j_client import Neo4jClient


class TestNeo4jClient:
    @pytest.fixture
    def client(self):
        config = SatMaestroConfig(neo4j_uri="bolt://localhost:7687")
        return Neo4jClient(config)

    def test_initial_state(self, client):
        assert not client.is_connected
        assert client._driver is None

    @pytest.mark.asyncio
    async def test_connect_missing_package(self, client):
        with patch.dict("sys.modules", {"neo4j": None}):
            with pytest.raises(ImportError, match="neo4j package required"):
                await client.connect()

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self, client):
        await client.close()  # should not raise
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_execute_without_connection(self, client):
        with pytest.raises(RuntimeError, match="not connected"):
            await client.execute("RETURN 1")

    @pytest.mark.asyncio
    async def test_execute_write_without_connection(self, client):
        with pytest.raises(RuntimeError, match="not connected"):
            await client.execute_write("CREATE (n:Test)")
