"""Tests for mass budget analyzer."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.mechanical.structural.mass_budget import MassBudgetAnalyzer
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus, Severity


class TestMassBudgetAnalyzer:

    @pytest.fixture
    def mock_bridge(self):
        bridge = AsyncMock()
        return bridge

    @pytest.fixture
    def analyzer(self, mock_bridge):
        return MassBudgetAnalyzer(mock_bridge, mass_margin=0.10)

    @pytest.mark.asyncio
    async def test_healthy_mass_budget(self, analyzer, mock_bridge):
        """No violations when mass within budget."""
        mock_bridge.neo4j_query.return_value = [
            {"name": "EPS", "total_mass": 8.0},
            {"name": "AOCS", "total_mass": 5.0},
            {"name": "COMMS", "total_mass": 3.0},
        ]
        result = await analyzer.analyze(budget=20.0)
        assert result.status == AnalysisStatus.PASS
        assert len(result.violations) == 0
        assert result.summary["total_mass"] == 16.0
        assert result.summary["margin"] > 0.10

    @pytest.mark.asyncio
    async def test_over_budget_violation(self, analyzer, mock_bridge):
        """ERROR when total mass exceeds budget."""
        mock_bridge.neo4j_query.return_value = [
            {"name": "EPS", "total_mass": 15.0},
            {"name": "AOCS", "total_mass": 10.0},
        ]
        result = await analyzer.analyze(budget=20.0)
        assert result.status == AnalysisStatus.FAIL
        assert any(v.severity == Severity.ERROR for v in result.violations)

    @pytest.mark.asyncio
    async def test_low_margin_warning(self, analyzer, mock_bridge):
        """WARNING when margin below threshold."""
        mock_bridge.neo4j_query.return_value = [
            {"name": "EPS", "total_mass": 18.5},
        ]
        result = await analyzer.analyze(budget=20.0)
        assert result.status == AnalysisStatus.WARN
        assert any(v.severity == Severity.WARNING for v in result.violations)

    @pytest.mark.asyncio
    async def test_subsystem_breakdown(self, analyzer, mock_bridge):
        """Summary includes per-subsystem breakdown."""
        mock_bridge.neo4j_query.return_value = [
            {"name": "EPS", "total_mass": 5.0},
            {"name": "AOCS", "total_mass": 3.0},
        ]
        result = await analyzer.analyze(budget=20.0)
        assert "subsystems" in result.summary
        assert len(result.summary["subsystems"]) == 2

    @pytest.mark.asyncio
    async def test_empty_graph(self, analyzer, mock_bridge):
        """Handles empty graph gracefully."""
        mock_bridge.neo4j_query.return_value = []
        result = await analyzer.analyze(budget=20.0)
        assert result.summary["total_mass"] == 0.0
