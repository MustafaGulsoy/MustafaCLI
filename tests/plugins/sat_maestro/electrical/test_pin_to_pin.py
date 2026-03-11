"""Tests for pin-to-pin analyzer."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.graph_models import (
    AnalysisStatus,
    Component,
    ComponentType,
    Pin,
    PinDirection,
    Severity,
)
from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.electrical.analyzers.pin_to_pin import PinToPinAnalyzer


@pytest.fixture
def analyzer(mock_bridge):
    return PinToPinAnalyzer(mock_bridge)


class TestPinToPinAnalyzer:
    @pytest.mark.asyncio
    async def test_all_connections_valid(self, analyzer, mock_bridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            # _get_all_connections
            [{"from_pin": "P1", "to_pin": "P2", "net_name": "NET1"}],
            # _find_path
            [{"node_ids": ["P1", "P2"], "nets": ["NET1"]}],
        ])

        result = await analyzer.verify()
        assert result.status == AnalysisStatus.PASS
        assert result.summary["connections_checked"] == 1
        assert result.summary["open_circuits"] == 0

    @pytest.mark.asyncio
    async def test_open_circuit_detected(self, analyzer, mock_bridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            # _get_all_connections
            [{"from_pin": "P1", "to_pin": "P2", "net_name": "NET1"}],
            # _find_path
            [],
        ])

        result = await analyzer.verify()
        assert result.status == AnalysisStatus.FAIL
        assert result.summary["open_circuits"] == 1
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "PIN-OPEN"
        assert result.violations[0].severity == Severity.ERROR

    @pytest.mark.asyncio
    async def test_no_connections(self, analyzer, mock_bridge):
        mock_bridge.neo4j_query = AsyncMock(return_value=[])
        result = await analyzer.verify()
        assert result.status == AnalysisStatus.PASS
        assert result.summary["connections_checked"] == 0

    @pytest.mark.asyncio
    async def test_multiple_open_circuits(self, analyzer, mock_bridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            # _get_all_connections
            [
                {"from_pin": "P1", "to_pin": "P2", "net_name": "NET1"},
                {"from_pin": "P3", "to_pin": "P4", "net_name": "NET2"},
                {"from_pin": "P5", "to_pin": "P6", "net_name": "NET3"},
            ],
            # _find_path for each (all empty = open)
            [], [], [],
        ])

        result = await analyzer.verify()
        assert result.status == AnalysisStatus.FAIL
        assert result.summary["open_circuits"] == 3
        assert len(result.violations) == 3

    @pytest.mark.asyncio
    async def test_subsystem_filter(self, analyzer, mock_bridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            # _get_all_connections
            [],
            # _get_components_by_subsystem
            [],
        ])
        result = await analyzer.verify(subsystem="EPS")
        assert result.metadata["subsystem"] == "EPS"
