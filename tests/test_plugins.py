"""
Tests for the plugin system
============================

Covers metadata, tool discovery, registry lifecycle, tool execution,
and entry-point loading.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from src.plugins.base import PluginBase, PluginMetadata, PluginTool, plugin_tool
from src.plugins.registry import PluginRegistry
from src.plugins.loader import load_entry_point_plugins
from src.core.tools import ToolResult


# ---------------------------------------------------------------------------
# Mock plugin used across tests
# ---------------------------------------------------------------------------

class MockPlugin(PluginBase):
    """A minimal plugin for testing purposes."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="mock-plugin",
            version="0.1.0",
            description="A mock plugin for testing",
            author="Test Author",
            tags=["test"],
        )

    @plugin_tool(name="greet", description="Greet someone by name")
    async def greet(self, name: str) -> ToolResult:
        return ToolResult(success=True, output=f"Hello, {name}!")

    @plugin_tool
    def add_numbers(self, a: int, b: int) -> ToolResult:
        """Add two numbers together."""
        return ToolResult(success=True, output=str(a + b))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPluginMetadata:
    def test_plugin_metadata(self) -> None:
        plugin = MockPlugin()
        meta = plugin.metadata
        assert meta.name == "mock-plugin"
        assert meta.version == "0.1.0"
        assert meta.description == "A mock plugin for testing"
        assert meta.author == "Test Author"
        assert meta.tags == ["test"]
        assert meta.requires == []
        assert meta.homepage == ""
        assert meta.license == ""


class TestPluginTools:
    def test_get_tools_returns_plugin_tools(self) -> None:
        plugin = MockPlugin()
        tools = plugin.get_tools()
        assert len(tools) == 2
        assert all(isinstance(t, PluginTool) for t in tools)
        names = {t.name for t in tools}
        assert "greet" in names
        assert "add_numbers" in names

    def test_tool_has_description(self) -> None:
        plugin = MockPlugin()
        tools = {t.name: t for t in plugin.get_tools()}
        assert tools["greet"].description == "Greet someone by name"
        assert tools["add_numbers"].description == "Add two numbers together."

    def test_tool_has_parameters(self) -> None:
        plugin = MockPlugin()
        tools = {t.name: t for t in plugin.get_tools()}
        params = tools["greet"].parameters
        assert params["type"] == "object"
        assert "name" in params["properties"]
        assert params["properties"]["name"]["type"] == "string"


class TestPluginRegistry:
    def test_register_and_list(self) -> None:
        registry = PluginRegistry()
        registry.register(MockPlugin)
        plugins = registry.list_plugins()
        assert len(plugins) == 1
        assert plugins[0].metadata.name == "mock-plugin"

    def test_get_plugin(self) -> None:
        registry = PluginRegistry()
        registry.register(MockPlugin)
        assert registry.get_plugin("mock-plugin") is not None
        assert registry.get_plugin("nonexistent") is None

    def test_unregister(self) -> None:
        registry = PluginRegistry()
        registry.register(MockPlugin)
        registry.unregister("mock-plugin")
        assert registry.get_plugin("mock-plugin") is None
        assert len(registry.list_plugins()) == 0

    def test_get_all_tools(self) -> None:
        registry = PluginRegistry()
        registry.register(MockPlugin)
        tools = registry.get_all_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "greet" in names
        assert "add_numbers" in names

    @pytest.mark.asyncio
    async def test_initialize_and_shutdown(self) -> None:
        registry = PluginRegistry()
        registry.register(MockPlugin)
        # Should not raise
        await registry.initialize_all()
        await registry.shutdown_all()


class TestPluginToolExecution:
    @pytest.mark.asyncio
    async def test_async_tool_execution(self) -> None:
        plugin = MockPlugin()
        tools = {t.name: t for t in plugin.get_tools()}
        result = await tools["greet"].execute(name="World")
        assert result.success is True
        assert result.output == "Hello, World!"

    @pytest.mark.asyncio
    async def test_sync_tool_execution(self) -> None:
        plugin = MockPlugin()
        tools = {t.name: t for t in plugin.get_tools()}
        result = await tools["add_numbers"].execute(a=3, b=4)
        assert result.success is True
        assert result.output == "7"


class TestEntryPointLoader:
    def test_loader_handles_empty_entry_points(self) -> None:
        """Loader should gracefully handle zero entry-point plugins."""
        registry = PluginRegistry()

        class FakeEPs:
            def select(self, group: str):
                return []

        with patch("src.plugins.loader.importlib.metadata.entry_points", return_value=FakeEPs()):
            load_entry_point_plugins(registry)

        assert len(registry.list_plugins()) == 0
