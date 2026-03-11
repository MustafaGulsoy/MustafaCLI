"""Tests for thermal checker (temperature limit validation)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus, Severity
from src.plugins.sat_maestro.mechanical.thermal.thermal_checker import ThermalChecker


@pytest.fixture
def mock_bridge() -> McpBridge:
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock()
    return bridge


def _make_nodes(nodes: list[dict]) -> list[dict]:
    return [{"n": node} for node in nodes]


def _make_conductances(links: list[dict]) -> list[dict]:
    return [{"c": link} for link in links]


class TestThermalChecker:

    @pytest.mark.asyncio
    async def test_all_within_limits(self, mock_bridge):
        """All nodes within operational range => PASS."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Battery", "temperature": 25.0,
                 "capacity": 100.0, "power_dissipation": 3.0,
                 "op_min_temp": -10.0, "op_max_temp": 45.0},
                {"id": "tn-2", "name": "OBC", "temperature": 35.0,
                 "capacity": 50.0, "power_dissipation": 5.0,
                 "op_min_temp": -20.0, "op_max_temp": 60.0},
            ]),
            _make_conductances([
                {"id": "tc-1", "node_a_id": "tn-1", "node_b_id": "tn-2",
                 "type": "CONDUCTION", "value": 1.0},
            ]),
        ]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        assert result.status == AnalysisStatus.PASS
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_node_exceeds_max_temp(self, mock_bridge):
        """Node above op_max_temp => ERROR."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Overheated", "temperature": 90.0,
                 "capacity": 100.0, "power_dissipation": 10.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([]),
        ]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        assert result.status == AnalysisStatus.FAIL
        assert any(v.severity == Severity.ERROR for v in result.violations)
        assert any("above" in v.message.lower() or "exceeds" in v.message.lower()
                    for v in result.violations)

    @pytest.mark.asyncio
    async def test_node_below_min_temp(self, mock_bridge):
        """Node below op_min_temp => ERROR."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Frozen", "temperature": -50.0,
                 "capacity": 100.0, "power_dissipation": 0.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([]),
        ]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        assert result.status == AnalysisStatus.FAIL
        assert any(v.severity == Severity.ERROR for v in result.violations)

    @pytest.mark.asyncio
    async def test_warning_near_max_limit(self, mock_bridge):
        """Node within 5 deg C of max => WARNING."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Warm", "temperature": 82.0,
                 "capacity": 100.0, "power_dissipation": 5.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([]),
        ]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        assert result.status == AnalysisStatus.WARN
        assert any(v.severity == Severity.WARNING for v in result.violations)

    @pytest.mark.asyncio
    async def test_warning_near_min_limit(self, mock_bridge):
        """Node within 5 deg C of min => WARNING."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Chilly", "temperature": -37.0,
                 "capacity": 100.0, "power_dissipation": 1.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([]),
        ]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        assert result.status == AnalysisStatus.WARN
        assert any(v.severity == Severity.WARNING for v in result.violations)

    @pytest.mark.asyncio
    async def test_gradient_check_exceeds_limit(self, mock_bridge):
        """Temperature gradient between connected nodes > 30 deg C => WARNING."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Hot", "temperature": 80.0,
                 "capacity": 100.0, "power_dissipation": 10.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
                {"id": "tn-2", "name": "Cold", "temperature": 10.0,
                 "capacity": 100.0, "power_dissipation": 0.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([
                {"id": "tc-1", "node_a_id": "tn-1", "node_b_id": "tn-2",
                 "type": "CONDUCTION", "value": 0.5},
            ]),
        ]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        assert result.status == AnalysisStatus.WARN
        assert any("gradient" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_gradient_within_limit(self, mock_bridge):
        """Temperature gradient <= 30 deg C => no gradient warning."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "A", "temperature": 30.0,
                 "capacity": 100.0, "power_dissipation": 5.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
                {"id": "tn-2", "name": "B", "temperature": 20.0,
                 "capacity": 100.0, "power_dissipation": 0.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([
                {"id": "tc-1", "node_a_id": "tn-1", "node_b_id": "tn-2",
                 "type": "CONDUCTION", "value": 1.0},
            ]),
        ]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        assert not any("gradient" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_empty_graph(self, mock_bridge):
        """No nodes => PASS."""
        mock_bridge.neo4j_query.side_effect = [[], []]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_heater_margin_warning(self, mock_bridge):
        """Heater margin < 25% => WARNING."""
        # Node near min temp with small margin
        # margin = (temp - op_min) / (op_max - op_min)
        # For temp=-30, min=-40, max=60: margin from min = (-30 - -40)/(60 - -40) = 10/100 = 10%
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "ColdUnit", "temperature": -30.0,
                 "capacity": 100.0, "power_dissipation": 1.0,
                 "op_min_temp": -40.0, "op_max_temp": 60.0},
            ]),
            _make_conductances([]),
        ]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        heater_violations = [v for v in result.violations if "heater" in v.message.lower()]
        assert len(heater_violations) > 0

    @pytest.mark.asyncio
    async def test_radiator_margin_warning(self, mock_bridge):
        """Radiator margin < 20% => WARNING."""
        # Node near max temp with small margin
        # margin from max = (op_max - temp) / (op_max - op_min)
        # For temp=75, min=-40, max=85: margin from max = (85-75)/(85--40) = 10/125 = 8%
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "HotUnit", "temperature": 75.0,
                 "capacity": 100.0, "power_dissipation": 10.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([]),
        ]

        checker = ThermalChecker(mock_bridge)
        result = await checker.analyze()

        radiator_violations = [v for v in result.violations if "radiator" in v.message.lower()]
        assert len(radiator_violations) > 0
