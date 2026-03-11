"""Tests for Harness Routing analyzer."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus, Severity
from src.plugins.sat_maestro.cross_discipline.harness_routing import HarnessRoutingAnalyzer


@pytest.fixture
def mock_bridge() -> McpBridge:
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock(return_value=[])
    return bridge


@pytest.fixture
def analyzer(mock_bridge: McpBridge) -> HarnessRoutingAnalyzer:
    return HarnessRoutingAnalyzer(mock_bridge)


class TestHarnessRouting:

    @pytest.mark.asyncio
    async def test_no_records_passes(self, analyzer: HarnessRoutingAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[[], []])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_normal_cable_passes(self, analyzer: HarnessRoutingAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{
                "n": {"id": "n1", "name": "PWR_BUS", "type": "POWER",
                       "cable_mass": 0.5, "cable_length": 1.5, "cable_diameter": 2.0},
                "a": {"id": "a1", "name": "S/C", "total_mass": 100.0},
                "connectors": [{"id": "conn1", "name": "J1", "series": "D-SUB"}],
            }],
            [{"total_mass": 100.0}],  # spacecraft mass
        ])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_long_cable_warning(self, analyzer: HarnessRoutingAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{
                "n": {"id": "n1", "name": "LONG_CABLE", "type": "SIGNAL",
                       "cable_mass": 1.0, "cable_length": 8.0, "cable_diameter": 1.0},
                "a": {"id": "a1", "name": "S/C", "total_mass": 200.0},
                "connectors": [{"id": "conn1", "name": "J1", "series": "Micro-D"}],
            }],
            [{"total_mass": 200.0}],
        ])
        result = await analyzer.analyze()
        assert any("length" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_no_connectors_warning(self, analyzer: HarnessRoutingAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{
                "n": {"id": "n1", "name": "ORPHAN_NET", "type": "SIGNAL",
                       "cable_mass": 0.1, "cable_length": 0.5, "cable_diameter": 0.5},
                "a": {"id": "a1", "name": "S/C", "total_mass": 100.0},
                "connectors": [],
            }],
            [{"total_mass": 100.0}],
        ])
        result = await analyzer.analyze()
        assert any("no connectors" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_bend_radius_violation(self, analyzer: HarnessRoutingAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{
                "n": {"id": "n1", "name": "TIGHT_CABLE", "type": "SIGNAL",
                       "cable_mass": 0.2, "cable_length": 1.0, "cable_diameter": 5.0,
                       "min_bend_radius": 10.0},  # 10mm < 5*6=30mm
                "a": {"id": "a1", "name": "S/C", "total_mass": 100.0},
                "connectors": [{"id": "c1", "name": "J1", "series": "X"}],
            }],
            [{"total_mass": 100.0}],
        ])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.FAIL
        assert any("bend radius" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_harness_mass_fraction_warning(self, analyzer: HarnessRoutingAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{
                "n": {"id": "n1", "name": "HEAVY_HARNESS", "type": "POWER",
                       "cable_mass": 12.0, "cable_length": 3.0, "cable_diameter": 3.0},
                "a": {"id": "a1", "name": "S/C", "total_mass": 100.0},
                "connectors": [{"id": "c1", "name": "J1", "series": "D-SUB"}],
            }],
            [{"total_mass": 100.0}],  # 12/100 = 12% > 8%
        ])
        result = await analyzer.analyze()
        assert any("mass fraction" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_summary_contains_mass(self, analyzer: HarnessRoutingAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{
                "n": {"id": "n1", "name": "Cable A", "type": "POWER",
                       "cable_mass": 0.5, "cable_length": 1.0, "cable_diameter": 2.0},
                "a": {"id": "a1", "name": "S/C", "total_mass": 100.0},
                "connectors": [{"id": "c1", "name": "J1", "series": "X"}],
            }],
            [{"total_mass": 100.0}],
        ])
        result = await analyzer.analyze()
        assert "total_harness_mass" in result.summary
        assert result.summary["total_harness_mass"] == 0.5
