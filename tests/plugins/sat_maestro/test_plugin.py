"""Tests for SAT-MAESTRO plugin entry point."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.plugins.sat_maestro.plugin import SatMaestroPlugin


class TestSatMaestroPlugin:
    @pytest.fixture
    def plugin(self):
        return SatMaestroPlugin()

    def test_metadata(self, plugin):
        meta = plugin.metadata
        assert meta.name == "sat-maestro"
        assert meta.version == "0.2.0"
        assert "satellite" in meta.tags
        assert "neo4j" in meta.requires

    def test_plugin_tools_registered(self, plugin):
        tools = plugin.get_tools()
        tool_names = [t.name for t in tools]
        assert "sat_import_kicad" in tool_names
        assert "sat_import_gerber" in tool_names
        assert "sat_analyze_pdf" in tool_names
        assert "sat_verify_pins" in tool_names
        assert "sat_power_budget" in tool_names
        assert "sat_check_connectors" in tool_names
        assert "sat_check_compliance" in tool_names
        assert "sat_report" in tool_names
        assert "sat_graph_query" in tool_names
        assert "sat_seed_rules" in tool_names

    def test_check_connected_not_connected(self, plugin):
        plugin.neo4j = None
        result = plugin._check_connected()
        assert result is not None
        assert not result.success
        assert "not connected" in result.error.lower()

    def test_check_connected_ok(self, plugin):
        plugin.neo4j = MagicMock()
        plugin.neo4j.is_connected = True
        result = plugin._check_connected()
        assert result is None

    @pytest.mark.asyncio
    async def test_shutdown_without_init(self, plugin):
        plugin.neo4j = None
        await plugin.shutdown()  # Should not raise

    @pytest.mark.asyncio
    async def test_tools_fail_without_connection(self, plugin):
        plugin.neo4j = None
        # Call the tool through PluginTool wrapper
        tools = plugin.get_tools()
        verify_tool = next(t for t in tools if t.name == "sat_verify_pins")
        result = await verify_tool.execute()
        assert not result.success

    @pytest.mark.asyncio
    async def test_graph_query_without_connection(self, plugin):
        plugin.neo4j = None
        tools = plugin.get_tools()
        query_tool = next(t for t in tools if t.name == "sat_graph_query")
        result = await query_tool.execute(query="RETURN 1")
        assert not result.success
