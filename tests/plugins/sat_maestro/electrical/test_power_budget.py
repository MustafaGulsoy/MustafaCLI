"""Tests for power budget analyzer."""
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
from src.plugins.sat_maestro.core.graph_ops import GraphOperations
from src.plugins.sat_maestro.electrical.analyzers.power_budget import PowerBudgetAnalyzer


@pytest.fixture
def mock_graph(mock_neo4j_client):
    return GraphOperations(mock_neo4j_client)


@pytest.fixture
def analyzer(mock_graph):
    return PowerBudgetAnalyzer(mock_graph, derating_factor=0.75)


class TestPowerBudgetAnalyzer:
    @pytest.mark.asyncio
    async def test_healthy_power_budget(self, analyzer, mock_graph):
        mock_graph.get_components_by_subsystem = AsyncMock(return_value=[
            Component(id="C1", name="REG1", type=ComponentType.IC, subsystem="EPS"),
        ])
        mock_graph.get_pins = AsyncMock(return_value=[
            Pin(id="P1", name="VOUT", direction=PinDirection.POWER,
                voltage=3.3, current_max=1.0, actual_current=0.5),
        ])

        result = await analyzer.analyze(subsystem="EPS")
        assert result.status == AnalysisStatus.PASS
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_derating_violation(self, analyzer, mock_graph):
        mock_graph.get_components_by_subsystem = AsyncMock(return_value=[
            Component(id="C1", name="REG1", type=ComponentType.IC, subsystem="EPS"),
        ])
        mock_graph.get_pins = AsyncMock(return_value=[
            Pin(id="P1", name="VOUT", direction=PinDirection.POWER,
                voltage=3.3, current_max=1.0, actual_current=0.9),
        ])

        result = await analyzer.analyze(subsystem="EPS")
        assert result.status == AnalysisStatus.FAIL
        derating_violations = [v for v in result.violations if v.rule_id == "POWER-DERATING"]
        assert len(derating_violations) == 1

    @pytest.mark.asyncio
    async def test_low_margin_warning(self, analyzer, mock_graph):
        mock_graph.get_components_by_subsystem = AsyncMock(return_value=[
            Component(id="C1", name="REG1", type=ComponentType.IC, subsystem="EPS"),
        ])
        # 70% usage = 30% margin, above 20% threshold and within derating (0.75)
        mock_graph.get_pins = AsyncMock(return_value=[
            Pin(id="P1", name="VOUT", direction=PinDirection.POWER,
                voltage=5.0, current_max=2.0, actual_current=0.7 * 2.0),
        ])

        result = await analyzer.analyze(subsystem="EPS")
        margin_warnings = [v for v in result.violations if v.rule_id == "POWER-MARGIN"]
        # actual=1.4, max=2.0, margin=1-1.4/2.0=0.3 (30%) > 20%
        # derating: 2.0 * 0.75 = 1.5 > 1.4, so no derating violation
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_no_power_pins(self, analyzer, mock_graph):
        mock_graph.get_components_by_subsystem = AsyncMock(return_value=[
            Component(id="C1", name="R1", type=ComponentType.PASSIVE, subsystem="EPS"),
        ])
        mock_graph.get_pins = AsyncMock(return_value=[
            Pin(id="P1", name="1", direction=PinDirection.BIDIRECTIONAL),
        ])

        result = await analyzer.analyze(subsystem="EPS")
        assert result.status == AnalysisStatus.PASS
        assert result.summary["rails_analyzed"] == 0

    @pytest.mark.asyncio
    async def test_summary_totals(self, analyzer, mock_graph):
        mock_graph.get_components_by_subsystem = AsyncMock(return_value=[
            Component(id="C1", name="REG1", type=ComponentType.IC, subsystem="EPS"),
        ])
        mock_graph.get_pins = AsyncMock(return_value=[
            Pin(id="P1", name="VOUT", direction=PinDirection.POWER,
                voltage=3.3, current_max=2.0, actual_current=0.5),
        ])

        result = await analyzer.analyze(subsystem="EPS")
        assert result.summary["total_supply_capacity"] == 2.0
        assert result.summary["total_consumption"] == 0.5
