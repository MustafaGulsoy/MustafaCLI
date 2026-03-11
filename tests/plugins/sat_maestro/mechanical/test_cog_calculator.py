"""Tests for center of gravity calculator."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.mechanical.structural.cog_calculator import CogCalculator
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus


class TestCogCalculator:

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def calc(self, mock_bridge):
        return CogCalculator(mock_bridge)

    @pytest.mark.asyncio
    async def test_simple_cog(self, calc, mock_bridge):
        """CoG of two equal masses at symmetric positions."""
        mock_bridge.neo4j_query.return_value = [
            {"mass": 10.0, "cog_x": 0.0, "cog_y": 0.0, "cog_z": 1.0},
            {"mass": 10.0, "cog_x": 0.0, "cog_y": 0.0, "cog_z": -1.0},
        ]
        result = await calc.calculate()
        assert abs(result.summary["cog_x"]) < 0.001
        assert abs(result.summary["cog_z"]) < 0.001  # symmetric -> z=0

    @pytest.mark.asyncio
    async def test_weighted_cog(self, calc, mock_bridge):
        """CoG weighted by mass."""
        mock_bridge.neo4j_query.return_value = [
            {"mass": 30.0, "cog_x": 0.0, "cog_y": 0.0, "cog_z": 0.0},
            {"mass": 10.0, "cog_x": 4.0, "cog_y": 0.0, "cog_z": 0.0},
        ]
        result = await calc.calculate()
        assert abs(result.summary["cog_x"] - 1.0) < 0.001  # (30*0+10*4)/40=1.0

    @pytest.mark.asyncio
    async def test_cog_offset_violation(self, calc, mock_bridge):
        """Violation when CoG offset exceeds limit."""
        mock_bridge.neo4j_query.return_value = [
            {"mass": 10.0, "cog_x": 10.0, "cog_y": 0.0, "cog_z": 0.0},
        ]
        result = await calc.calculate(max_offset=5.0)
        assert result.status == AnalysisStatus.FAIL

    @pytest.mark.asyncio
    async def test_empty_graph(self, calc, mock_bridge):
        """Handles no structures gracefully."""
        mock_bridge.neo4j_query.return_value = []
        result = await calc.calculate()
        assert result.summary["total_mass"] == 0.0
