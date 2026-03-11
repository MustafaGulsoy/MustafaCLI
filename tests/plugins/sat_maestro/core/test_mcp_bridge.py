"""Tests for MCP Bridge - central MCP communication layer."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge, McpServerConfig


class TestMcpBridge:
    """Test MCP Bridge initialization and server management."""

    def test_create_bridge_with_config(self):
        """Bridge accepts server configurations."""
        config = {
            "neo4j": McpServerConfig(name="neo4j", command="npx", args=["-y", "@neo4j/mcp-neo4j"]),
            "freecad": McpServerConfig(name="freecad", command="python", args=["-m", "freecad_mcp"]),
        }
        bridge = McpBridge(servers=config)
        assert "neo4j" in bridge.servers
        assert "freecad" in bridge.servers

    def test_bridge_not_connected_by_default(self):
        bridge = McpBridge(servers={})
        assert not bridge.is_connected("neo4j")

    @pytest.mark.asyncio
    async def test_call_tool_on_disconnected_server_raises(self):
        bridge = McpBridge(servers={})
        with pytest.raises(RuntimeError, match="not connected"):
            await bridge.call_tool("neo4j", "read_neo4j_cypher", {"query": "RETURN 1"})
