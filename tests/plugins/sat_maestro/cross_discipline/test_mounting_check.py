"""Tests for Mounting Check analyzer."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus, Severity
from src.plugins.sat_maestro.cross_discipline.mounting_check import MountingCheckAnalyzer


@pytest.fixture
def mock_bridge() -> McpBridge:
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock(return_value=[])
    return bridge


@pytest.fixture
def analyzer(mock_bridge: McpBridge) -> MountingCheckAnalyzer:
    return MountingCheckAnalyzer(mock_bridge)


class TestMountingCheck:

    @pytest.mark.asyncio
    async def test_no_records_passes(self, analyzer: MountingCheckAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS
        assert result.summary["mounts_checked"] == 0

    @pytest.mark.asyncio
    async def test_compatible_mounting_passes(self, analyzer: MountingCheckAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 5.0, "material": "Al7075",
                  "subsystem": "STR", "mount_capacity": 20.0,
                  "mount_pattern": "M4x4", "mount_points": 4},
            "c": {"id": "c1", "name": "Star Tracker", "mass": 3.0,
                  "mounting_pattern": "M4x4", "mounting_points": 4},
        }])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_insufficient_capacity_error(self, analyzer: MountingCheckAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Bracket B", "mass": 1.0, "material": "Al6061",
                  "subsystem": "STR", "mount_capacity": 3.0,
                  "mount_pattern": "M4x4", "mount_points": 4},
            "c": {"id": "c1", "name": "Battery", "mass": 8.0,
                  "mounting_pattern": "M4x4", "mounting_points": 4},
        }])
        result = await analyzer.analyze()
        # Required capacity = 8.0 * 1.5 = 12.0 > 3.0
        assert result.status == AnalysisStatus.FAIL
        assert any("insufficient" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_bolt_pattern_mismatch_error(self, analyzer: MountingCheckAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 5.0, "material": "Al7075",
                  "subsystem": "STR", "mount_capacity": 50.0,
                  "mount_pattern": "M4x4", "mount_points": 4},
            "c": {"id": "c1", "name": "RW Unit", "mass": 5.0,
                  "mounting_pattern": "M6x6", "mounting_points": 4},
        }])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.FAIL
        assert any("pattern mismatch" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_insufficient_mount_points_error(self, analyzer: MountingCheckAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 5.0, "material": "Al7075",
                  "subsystem": "STR", "mount_capacity": 50.0,
                  "mount_pattern": "M4x4", "mount_points": 2},
            "c": {"id": "c1", "name": "Thruster", "mass": 2.0,
                  "mounting_pattern": "M4x4", "mounting_points": 4},
        }])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.FAIL
        assert any("mount points" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_no_pattern_info_passes(self, analyzer: MountingCheckAnalyzer, mock_bridge: McpBridge):
        """Missing pattern/capacity info should not cause false violations."""
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 5.0, "material": "Al7075",
                  "subsystem": "STR"},
            "c": {"id": "c1", "name": "Sensor", "mass": 0.5},
        }])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_summary_contains_counts(self, analyzer: MountingCheckAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[{
            "s": {"id": "s1", "name": "Panel A", "mass": 5.0, "material": "Al7075",
                  "subsystem": "STR"},
            "c": {"id": "c1", "name": "Sensor", "mass": 0.5},
        }])
        result = await analyzer.analyze()
        assert result.summary["mounts_checked"] == 1
