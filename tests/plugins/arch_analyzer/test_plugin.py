"""Tests for ArchAnalyzerPlugin."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.plugins.arch_analyzer.plugin import ArchAnalyzerPlugin
from src.plugins.base import PluginBase, PluginMetadata


class TestPluginMetadata:
    """Tests for ArchAnalyzerPlugin metadata."""

    def test_is_plugin_base(self) -> None:
        plugin = ArchAnalyzerPlugin()
        assert isinstance(plugin, PluginBase)

    def test_metadata_name(self) -> None:
        plugin = ArchAnalyzerPlugin()
        assert plugin.metadata.name == "arch-analyzer"

    def test_metadata_has_version(self) -> None:
        plugin = ArchAnalyzerPlugin()
        assert plugin.metadata.version

    def test_metadata_has_description(self) -> None:
        plugin = ArchAnalyzerPlugin()
        assert len(plugin.metadata.description) > 10

    def test_metadata_no_external_requires(self) -> None:
        plugin = ArchAnalyzerPlugin()
        assert plugin.metadata.requires == []


class TestPluginTools:
    """Tests for tool discovery."""

    @pytest.fixture
    def initialized_plugin(self) -> ArchAnalyzerPlugin:
        """Return an ArchAnalyzerPlugin after calling initialize()."""
        import asyncio
        plugin = ArchAnalyzerPlugin()
        asyncio.get_event_loop().run_until_complete(plugin.initialize())
        return plugin

    def test_get_tools_returns_list(self, initialized_plugin: ArchAnalyzerPlugin) -> None:
        tools = initialized_plugin.get_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_tools_have_names(self, initialized_plugin: ArchAnalyzerPlugin) -> None:
        tools = initialized_plugin.get_tools()
        names = [t.name for t in tools]
        assert "arch_analyze_structure" in names or "arch_full_report" in names

    def test_tools_have_descriptions(self, initialized_plugin: ArchAnalyzerPlugin) -> None:
        tools = initialized_plugin.get_tools()
        for tool in tools:
            assert tool.description, f"Tool {tool.name} has no description"

    def test_tools_have_parameters(self, initialized_plugin: ArchAnalyzerPlugin) -> None:
        tools = initialized_plugin.get_tools()
        for tool in tools:
            assert isinstance(tool.parameters, dict)
