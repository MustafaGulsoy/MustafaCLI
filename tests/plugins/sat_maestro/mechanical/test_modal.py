"""Tests for modal analysis evaluator."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.mechanical.vibration.modal import ModalAnalyzer
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus


class TestModalAnalyzer:

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def analyzer(self, mock_bridge):
        return ModalAnalyzer(mock_bridge)

    @pytest.mark.asyncio
    async def test_pass_all_frequencies_above_limits(self, analyzer):
        """All modes above ECSS limits -> PASS."""
        modes = [
            {"mode": 1, "frequency_hz": 40.0, "eigenvalue": 63165.0},
            {"mode": 2, "frequency_hz": 55.0, "eigenvalue": 119460.0},
            {"mode": 3, "frequency_hz": 80.0, "eigenvalue": 252610.0},
        ]
        result = await analyzer.evaluate(modes)
        assert result.status == AnalysisStatus.PASS
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_fail_lateral_frequency_below_limit(self, analyzer):
        """First lateral mode below 15 Hz -> FAIL."""
        modes = [
            {"mode": 1, "frequency_hz": 10.0, "eigenvalue": 3948.0},
            {"mode": 2, "frequency_hz": 40.0, "eigenvalue": 63165.0},
        ]
        result = await analyzer.evaluate(modes, min_lateral_hz=15.0)
        assert result.status == AnalysisStatus.FAIL
        assert any("lateral" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_fail_axial_frequency_below_limit(self, analyzer):
        """Axial mode below 35 Hz -> FAIL."""
        modes = [
            {"mode": 1, "frequency_hz": 20.0, "eigenvalue": 15791.0},
        ]
        result = await analyzer.evaluate(modes, min_axial_hz=35.0)
        assert result.status == AnalysisStatus.FAIL
        assert any("axial" in v.message.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_empty_modes_list(self, analyzer):
        """Empty modes list -> WARNING."""
        result = await analyzer.evaluate([])
        assert result.status == AnalysisStatus.WARN

    @pytest.mark.asyncio
    async def test_custom_frequency_limits(self, analyzer):
        """Custom frequency limits are respected."""
        modes = [
            {"mode": 1, "frequency_hz": 25.0, "eigenvalue": 24674.0},
        ]
        # With default 15 Hz lateral limit -> PASS
        result = await analyzer.evaluate(modes, min_lateral_hz=15.0, min_axial_hz=20.0)
        assert result.status == AnalysisStatus.PASS

        # With higher lateral limit -> FAIL
        result = await analyzer.evaluate(modes, min_lateral_hz=30.0)
        assert result.status == AnalysisStatus.FAIL

    @pytest.mark.asyncio
    async def test_summary_contains_mode_info(self, analyzer):
        """Summary includes mode count and first frequency."""
        modes = [
            {"mode": 1, "frequency_hz": 42.0, "eigenvalue": 69633.0},
            {"mode": 2, "frequency_hz": 58.0, "eigenvalue": 132825.0},
        ]
        result = await analyzer.evaluate(modes)
        assert result.summary["mode_count"] == 2
        assert result.summary["first_frequency_hz"] == 42.0
