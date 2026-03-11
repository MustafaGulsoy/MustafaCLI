"""Tests for Mass-Thermal correlation analyzer."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus, Severity
from src.plugins.sat_maestro.cross_discipline.mass_thermal import MassThermalAnalyzer


@pytest.fixture
def mock_bridge() -> McpBridge:
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock(return_value=[])
    return bridge


@pytest.fixture
def analyzer(mock_bridge: McpBridge) -> MassThermalAnalyzer:
    return MassThermalAnalyzer(mock_bridge)


class TestMassThermalCorrelation:

    @pytest.mark.asyncio
    async def test_no_records_passes(self, analyzer: MassThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS
        assert result.analyzer == "MassThermalAnalyzer"

    @pytest.mark.asyncio
    async def test_normal_component_passes(self, analyzer: MassThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 2.0, "subsystem": "STR"},
            "c": {"id": "c1", "name": "OBC"},
            "tn": {"id": "tn1", "name": "OBC Thermal", "temperature": 40.0,
                   "power_dissipation": 5.0, "op_min_temp": -20, "op_max_temp": 70},
        }])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_missing_thermal_node_warning(self, analyzer: MassThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 2.0, "subsystem": "STR"},
            "c": {"id": "c1", "name": "OBC"},
            "tn": None,
        }])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.WARN
        assert any("no thermal node" in v.message for v in result.violations)

    @pytest.mark.asyncio
    async def test_heavy_hot_component_warning(self, analyzer: MassThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 10.0, "subsystem": "STR"},
            "c": {"id": "c1", "name": "Battery"},
            "tn": {"id": "tn1", "name": "Battery Thermal", "temperature": 70.0,
                   "power_dissipation": 20.0, "op_min_temp": -10, "op_max_temp": 80},
        }])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.WARN
        assert any("Heavy+hot" in v.message for v in result.violations)

    @pytest.mark.asyncio
    async def test_high_power_density_warning(self, analyzer: MassThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 0.5, "subsystem": "STR"},
            "c": {"id": "c1", "name": "SSPA"},
            "tn": {"id": "tn1", "name": "SSPA Thermal", "temperature": 50.0,
                   "power_dissipation": 40.0, "op_min_temp": -10, "op_max_temp": 80},
        }])
        result = await analyzer.analyze()
        # 40W / 0.5kg = 80 W/kg > 50 W/kg threshold
        assert any("power density" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_summary_contains_counts(self, analyzer: MassThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 2.0, "subsystem": "STR"},
            "c": {"id": "c1", "name": "OBC"},
            "tn": {"id": "tn1", "name": "OBC Thermal", "temperature": 40.0,
                   "power_dissipation": 5.0, "op_min_temp": -20, "op_max_temp": 70},
        }])
        result = await analyzer.analyze()
        assert "records_checked" in result.summary
        assert result.summary["records_checked"] == 1
