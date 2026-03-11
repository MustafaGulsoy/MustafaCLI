"""Shared test fixtures for SAT-MAESTRO tests."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.plugins.sat_maestro.config import SatMaestroConfig
from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.neo4j_client import Neo4jClient
from src.plugins.sat_maestro.core.graph_ops import GraphOperations


@pytest.fixture
def config() -> SatMaestroConfig:
    return SatMaestroConfig(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="test",
        neo4j_database="test",
    )


@pytest.fixture
def mock_neo4j_client(config) -> Neo4jClient:
    client = Neo4jClient(config)
    client._driver = MagicMock()
    client.execute = AsyncMock(return_value=[])
    client.execute_write = AsyncMock(return_value=[])
    return client


@pytest.fixture
def graph_ops(mock_neo4j_client) -> GraphOperations:
    return GraphOperations(mock_neo4j_client)


@pytest.fixture
def mock_bridge() -> McpBridge:
    """Create a mock MCP bridge with neo4j_query/neo4j_write as AsyncMocks."""
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock(return_value=[])
    bridge.neo4j_write = AsyncMock(return_value=[])
    bridge.call_tool = AsyncMock(return_value={})
    return bridge
