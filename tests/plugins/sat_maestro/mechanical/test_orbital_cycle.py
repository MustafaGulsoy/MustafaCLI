"""Tests for orbital thermal cycle analyzer."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus, Severity
from src.plugins.sat_maestro.mechanical.thermal.orbital_cycle import OrbitalCycleAnalyzer


@pytest.fixture
def mock_bridge() -> McpBridge:
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock()
    return bridge


def _make_nodes(nodes: list[dict]) -> list[dict]:
    return [{"n": node} for node in nodes]


def _make_conductances(links: list[dict]) -> list[dict]:
    return [{"c": link} for link in links]


class TestOrbitalCycleAnalyzer:

    @pytest.mark.asyncio
    async def test_basic_orbit_cycle(self, mock_bridge):
        """Run a basic orbit cycle and get min/max temperatures."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Panel", "temperature": 20.0,
                 "capacity": 200.0, "power_dissipation": 5.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
                {"id": "tn-2", "name": "Radiator", "temperature": -10.0,
                 "capacity": 300.0, "power_dissipation": 0.0,
                 "op_min_temp": -60.0, "op_max_temp": 40.0},
            ]),
            _make_conductances([
                {"id": "tc-1", "node_a_id": "tn-1", "node_b_id": "tn-2",
                 "type": "CONDUCTION", "value": 1.0},
            ]),
        ]

        analyzer = OrbitalCycleAnalyzer(mock_bridge)
        result = await analyzer.analyze(
            orbit_period=5400.0,
            eclipse_fraction=0.35,
            solar_flux=1361.0,
            albedo=0.3,
        )

        assert result.status in (AnalysisStatus.PASS, AnalysisStatus.WARN, AnalysisStatus.FAIL)
        assert "min_temperatures" in result.summary
        assert "max_temperatures" in result.summary
        assert "tn-1" in result.summary["min_temperatures"]
        assert "tn-1" in result.summary["max_temperatures"]

    @pytest.mark.asyncio
    async def test_eclipse_causes_cooling(self, mock_bridge):
        """During eclipse, nodes should cool down from sunlit phase."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "SolarPanel", "temperature": 50.0,
                 "capacity": 100.0, "power_dissipation": 2.0,
                 "op_min_temp": -100.0, "op_max_temp": 120.0},
            ]),
            _make_conductances([]),
        ]

        analyzer = OrbitalCycleAnalyzer(mock_bridge)
        result = await analyzer.analyze(
            orbit_period=5400.0,
            eclipse_fraction=0.35,
            solar_flux=1361.0,
            albedo=0.3,
        )

        mins = result.summary["min_temperatures"]
        maxs = result.summary["max_temperatures"]
        # Min temperature should be less than max temperature
        assert mins["tn-1"] < maxs["tn-1"]

    @pytest.mark.asyncio
    async def test_hot_case_violation(self, mock_bridge):
        """Node exceeding max temp during hot case => ERROR."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "SensitiveUnit", "temperature": 80.0,
                 "capacity": 50.0, "power_dissipation": 20.0,
                 "op_min_temp": -20.0, "op_max_temp": 60.0},
            ]),
            _make_conductances([]),
        ]

        analyzer = OrbitalCycleAnalyzer(mock_bridge)
        result = await analyzer.analyze(
            orbit_period=5400.0,
            eclipse_fraction=0.2,
            solar_flux=1361.0,
            albedo=0.3,
        )

        # With high power and small capacity, node will exceed 60 deg C
        assert result.status == AnalysisStatus.FAIL
        assert any(v.severity == Severity.ERROR for v in result.violations)

    @pytest.mark.asyncio
    async def test_empty_graph(self, mock_bridge):
        """No nodes => PASS."""
        mock_bridge.neo4j_query.side_effect = [[], []]

        analyzer = OrbitalCycleAnalyzer(mock_bridge)
        result = await analyzer.analyze()

        assert result.status == AnalysisStatus.PASS
        assert result.summary["min_temperatures"] == {}

    @pytest.mark.asyncio
    async def test_default_parameters(self, mock_bridge):
        """Analyzer works with default orbital parameters."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Test", "temperature": 20.0,
                 "capacity": 500.0, "power_dissipation": 3.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([]),
        ]

        analyzer = OrbitalCycleAnalyzer(mock_bridge)
        result = await analyzer.analyze()  # Use defaults

        assert result.analyzer == "orbital_cycle"
        assert "orbit_period" in result.metadata

    @pytest.mark.asyncio
    async def test_multi_node_coupled_orbit(self, mock_bridge):
        """Multiple coupled nodes through an orbital cycle."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "External", "temperature": 30.0,
                 "capacity": 100.0, "power_dissipation": 0.0,
                 "op_min_temp": -80.0, "op_max_temp": 100.0},
                {"id": "tn-2", "name": "Internal", "temperature": 25.0,
                 "capacity": 500.0, "power_dissipation": 0.0,
                 "op_min_temp": -80.0, "op_max_temp": 100.0},
            ]),
            _make_conductances([
                {"id": "tc-1", "node_a_id": "tn-1", "node_b_id": "tn-2",
                 "type": "CONDUCTION", "value": 0.5},
            ]),
        ]

        analyzer = OrbitalCycleAnalyzer(mock_bridge)
        result = await analyzer.analyze(
            orbit_period=5400.0,
            eclipse_fraction=0.35,
            solar_flux=1361.0,
        )

        assert "tn-1" in result.summary["min_temperatures"]
        assert "tn-2" in result.summary["min_temperatures"]
        # With equal power (0W) but lower capacity, external node should have
        # larger temperature swing than higher-capacity internal node
        ext_range = result.summary["max_temperatures"]["tn-1"] - result.summary["min_temperatures"]["tn-1"]
        int_range = result.summary["max_temperatures"]["tn-2"] - result.summary["min_temperatures"]["tn-2"]
        assert ext_range >= int_range

    @pytest.mark.asyncio
    async def test_cold_case_violation(self, mock_bridge):
        """Node dropping below min temp during eclipse => ERROR."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "ColdSensitive", "temperature": -10.0,
                 "capacity": 30.0, "power_dissipation": 0.5,
                 "op_min_temp": -15.0, "op_max_temp": 50.0},
            ]),
            _make_conductances([]),
        ]

        analyzer = OrbitalCycleAnalyzer(mock_bridge)
        result = await analyzer.analyze(
            orbit_period=5400.0,
            eclipse_fraction=0.5,  # long eclipse
            solar_flux=1361.0,
        )

        # With low capacity, low power, and long eclipse, node will drop below -15
        assert result.status == AnalysisStatus.FAIL
