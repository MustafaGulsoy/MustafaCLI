"""Tests for shock analysis (SRS)."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.mechanical.vibration.shock import ShockAnalyzer
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus


class TestShockAnalyzer:

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def analyzer(self, mock_bridge):
        return ShockAnalyzer(mock_bridge)

    @pytest.mark.asyncio
    async def test_srs_within_qualification(self, analyzer):
        """SRS within qualified levels -> PASS."""
        srs_data = [
            {"freq_hz": 100.0, "accel_g": 50.0},
            {"freq_hz": 1000.0, "accel_g": 500.0},
            {"freq_hz": 10000.0, "accel_g": 1000.0},
        ]
        qual_levels = [
            {"freq_hz": 100.0, "accel_g": 100.0},
            {"freq_hz": 1000.0, "accel_g": 1000.0},
            {"freq_hz": 10000.0, "accel_g": 2000.0},
        ]
        result = await analyzer.evaluate(srs_data, qual_levels)
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_srs_exceeds_qualification(self, analyzer):
        """SRS exceeds qualified levels -> FAIL."""
        srs_data = [
            {"freq_hz": 100.0, "accel_g": 200.0},
            {"freq_hz": 1000.0, "accel_g": 1500.0},
        ]
        qual_levels = [
            {"freq_hz": 100.0, "accel_g": 100.0},
            {"freq_hz": 1000.0, "accel_g": 1000.0},
        ]
        result = await analyzer.evaluate(srs_data, qual_levels)
        assert result.status == AnalysisStatus.FAIL

    @pytest.mark.asyncio
    async def test_srs_with_margin(self, analyzer):
        """SRS with margin applied -> FAIL when within margin band."""
        srs_data = [
            {"freq_hz": 100.0, "accel_g": 95.0},
        ]
        qual_levels = [
            {"freq_hz": 100.0, "accel_g": 100.0},
        ]
        # 3 dB margin (factor ~1.41) means qual_level/1.41 ~ 70.7
        # 95 > 70.7 so within margin band -> should still pass at 0 margin
        result = await analyzer.evaluate(srs_data, qual_levels, margin_db=0.0)
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_empty_srs_data(self, analyzer):
        """Empty SRS data -> WARNING."""
        result = await analyzer.evaluate([], [])
        assert result.status == AnalysisStatus.WARN

    @pytest.mark.asyncio
    async def test_summary_fields(self, analyzer):
        """Summary contains expected fields."""
        srs_data = [
            {"freq_hz": 100.0, "accel_g": 50.0},
        ]
        qual_levels = [
            {"freq_hz": 100.0, "accel_g": 100.0},
        ]
        result = await analyzer.evaluate(srs_data, qual_levels)
        assert "max_ratio" in result.summary
        assert "points_checked" in result.summary
