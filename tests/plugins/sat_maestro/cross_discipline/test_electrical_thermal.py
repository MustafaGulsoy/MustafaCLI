"""Tests for Electrical-Thermal correlation analyzer."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus, Severity
from src.plugins.sat_maestro.cross_discipline.electrical_thermal import ElectricalThermalAnalyzer


@pytest.fixture
def mock_bridge() -> McpBridge:
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock(return_value=[])
    return bridge


@pytest.fixture
def analyzer(mock_bridge: McpBridge) -> ElectricalThermalAnalyzer:
    return ElectricalThermalAnalyzer(mock_bridge)


class TestElectricalThermalMapping:

    @pytest.mark.asyncio
    async def test_no_records_passes(self, analyzer: ElectricalThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS
        assert result.summary["components_checked"] == 0

    @pytest.mark.asyncio
    async def test_matched_power_passes(self, analyzer: ElectricalThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "c": {"id": "c1", "name": "OBC", "power_dissipation": 10.0, "subsystem": "CDMS"},
            "tn": {"id": "tn1", "name": "OBC Thermal", "power_dissipation": 10.0,
                   "temperature": 45.0},
        }])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_missing_thermal_node_error(self, analyzer: ElectricalThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "c": {"id": "c1", "name": "SSPA", "power_dissipation": 25.0, "subsystem": "COMM"},
            "tn": None,
        }])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.FAIL
        assert any(v.severity == Severity.ERROR for v in result.violations)
        assert any("no thermal node" in v.message for v in result.violations)

    @pytest.mark.asyncio
    async def test_power_mismatch_warning(self, analyzer: ElectricalThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "c": {"id": "c1", "name": "RW", "power_dissipation": 10.0, "subsystem": "AOCS"},
            "tn": {"id": "tn1", "name": "RW Thermal", "power_dissipation": 7.0,
                   "temperature": 40.0},
        }])
        result = await analyzer.analyze()
        # Mismatch = |10-7|/10 = 30% > 10%
        assert result.status == AnalysisStatus.WARN
        assert any("mismatch" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_small_mismatch_passes(self, analyzer: ElectricalThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "c": {"id": "c1", "name": "Sensor", "power_dissipation": 10.0, "subsystem": "PL"},
            "tn": {"id": "tn1", "name": "Sensor Thermal", "power_dissipation": 9.5,
                   "temperature": 35.0},
        }])
        result = await analyzer.analyze()
        # Mismatch = |10-9.5|/10 = 5% < 10%
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_power_totals_in_summary(self, analyzer: ElectricalThermalAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[
            {
                "c": {"id": "c1", "name": "A", "power_dissipation": 10.0, "subsystem": "X"},
                "tn": {"id": "tn1", "name": "A TN", "power_dissipation": 10.0, "temperature": 30},
            },
            {
                "c": {"id": "c2", "name": "B", "power_dissipation": 5.0, "subsystem": "Y"},
                "tn": {"id": "tn2", "name": "B TN", "power_dissipation": 5.0, "temperature": 25},
            },
        ])
        result = await analyzer.analyze()
        assert result.summary["total_electrical_power"] == 15.0
        assert result.summary["total_thermal_power"] == 15.0
