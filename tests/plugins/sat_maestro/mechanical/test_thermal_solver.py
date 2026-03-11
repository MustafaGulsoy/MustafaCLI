"""Tests for thermal node model (lumped-parameter solver)."""
from __future__ import annotations

import pytest
import numpy as np
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus
from src.plugins.sat_maestro.mechanical.thermal.node_model import ThermalNodeModel


@pytest.fixture
def mock_bridge() -> McpBridge:
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock()
    bridge.neo4j_write = AsyncMock()
    return bridge


def _make_nodes(nodes: list[dict]) -> list[dict]:
    """Helper to create Neo4j-style node records."""
    return [{"n": node} for node in nodes]


def _make_conductances(links: list[dict]) -> list[dict]:
    """Helper to create Neo4j-style conductance records."""
    return [{"c": link} for link in links]


class TestThermalNodeModel:

    @pytest.mark.asyncio
    async def test_simple_two_node(self, mock_bridge):
        """Two nodes connected by a single conductance link."""
        mock_bridge.neo4j_query.side_effect = [
            # First call: query thermal nodes
            _make_nodes([
                {"id": "tn-1", "name": "Source", "temperature": 20.0,
                 "capacity": 100.0, "power_dissipation": 10.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
                {"id": "tn-2", "name": "Sink", "temperature": 20.0,
                 "capacity": 100.0, "power_dissipation": 0.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            # Second call: query conductance links
            _make_conductances([
                {"id": "tc-1", "node_a_id": "tn-1", "node_b_id": "tn-2",
                 "type": "CONDUCTION", "value": 0.5},
            ]),
        ]

        solver = ThermalNodeModel(mock_bridge)
        result = await solver.analyze()

        assert result.status == AnalysisStatus.PASS
        temps = result.summary["temperatures"]
        # With 10W on node 1, conductance 0.5 W/K, and boundary sink at node 2:
        # In steady-state with G matrix: G11=0.5, G12=-0.5, G21=-0.5, G22=0.5
        # But this is singular; we need a boundary condition.
        # The solver should add a reference/boundary term.
        # Node 1 should be hotter than node 2
        assert temps["tn-1"] > temps["tn-2"]

    @pytest.mark.asyncio
    async def test_three_node_network(self, mock_bridge):
        """Three-node thermal network with known solution."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Hot", "temperature": 20.0,
                 "capacity": 100.0, "power_dissipation": 5.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
                {"id": "tn-2", "name": "Mid", "temperature": 20.0,
                 "capacity": 100.0, "power_dissipation": 2.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
                {"id": "tn-3", "name": "Cold", "temperature": 20.0,
                 "capacity": 200.0, "power_dissipation": 0.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([
                {"id": "tc-1", "node_a_id": "tn-1", "node_b_id": "tn-2",
                 "type": "CONDUCTION", "value": 1.0},
                {"id": "tc-2", "node_a_id": "tn-2", "node_b_id": "tn-3",
                 "type": "CONDUCTION", "value": 0.5},
            ]),
        ]

        solver = ThermalNodeModel(mock_bridge)
        result = await solver.analyze()

        assert result.status == AnalysisStatus.PASS
        temps = result.summary["temperatures"]
        assert len(temps) == 3
        # Temperature should decrease from hot to cold
        assert temps["tn-1"] > temps["tn-2"]
        assert temps["tn-2"] > temps["tn-3"]

    @pytest.mark.asyncio
    async def test_no_nodes_returns_pass(self, mock_bridge):
        """Empty graph should return PASS with empty results."""
        mock_bridge.neo4j_query.side_effect = [[], []]

        solver = ThermalNodeModel(mock_bridge)
        result = await solver.analyze()

        assert result.status == AnalysisStatus.PASS
        assert result.summary["temperatures"] == {}

    @pytest.mark.asyncio
    async def test_single_node_no_links(self, mock_bridge):
        """Single node with power but no conductance links."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Isolated", "temperature": 20.0,
                 "capacity": 100.0, "power_dissipation": 5.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([]),
        ]

        solver = ThermalNodeModel(mock_bridge)
        result = await solver.analyze()

        # Single isolated node with power: solver should handle gracefully
        assert result.status in (AnalysisStatus.PASS, AnalysisStatus.WARN)

    @pytest.mark.asyncio
    async def test_result_stores_node_temperatures(self, mock_bridge):
        """Result summary contains temperature for each node by ID."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-a", "name": "A", "temperature": 20.0,
                 "capacity": 50.0, "power_dissipation": 3.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
                {"id": "tn-b", "name": "B", "temperature": 20.0,
                 "capacity": 50.0, "power_dissipation": 0.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
            ]),
            _make_conductances([
                {"id": "tc-1", "node_a_id": "tn-a", "node_b_id": "tn-b",
                 "type": "CONDUCTION", "value": 1.0},
            ]),
        ]

        solver = ThermalNodeModel(mock_bridge)
        result = await solver.analyze()

        assert "tn-a" in result.summary["temperatures"]
        assert "tn-b" in result.summary["temperatures"]
        assert result.analyzer == "thermal_node_model"

    @pytest.mark.asyncio
    async def test_boundary_node_with_zero_power(self, mock_bridge):
        """A node with zero power acts as a heat sink at reference temperature."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "Heater", "temperature": 20.0,
                 "capacity": 100.0, "power_dissipation": 20.0,
                 "op_min_temp": -40.0, "op_max_temp": 85.0},
                {"id": "tn-2", "name": "Radiator", "temperature": -20.0,
                 "capacity": 500.0, "power_dissipation": 0.0,
                 "op_min_temp": -60.0, "op_max_temp": 40.0},
            ]),
            _make_conductances([
                {"id": "tc-1", "node_a_id": "tn-1", "node_b_id": "tn-2",
                 "type": "RADIATION", "value": 0.8},
            ]),
        ]

        solver = ThermalNodeModel(mock_bridge)
        result = await solver.analyze()

        temps = result.summary["temperatures"]
        # Node with power should be warmer
        assert temps["tn-1"] > temps["tn-2"]

    @pytest.mark.asyncio
    async def test_writes_results_back_to_neo4j(self, mock_bridge):
        """After solving, temperatures are written back to Neo4j."""
        mock_bridge.neo4j_query.side_effect = [
            _make_nodes([
                {"id": "tn-1", "name": "A", "temperature": 20.0,
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

        solver = ThermalNodeModel(mock_bridge)
        await solver.analyze()

        # Should have called neo4j_write to store results
        assert mock_bridge.neo4j_write.called
