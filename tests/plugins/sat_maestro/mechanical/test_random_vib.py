"""Tests for random vibration analyzer."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.mechanical.vibration.random_vib import RandomVibAnalyzer
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus


class TestRandomVibAnalyzer:

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def analyzer(self, mock_bridge):
        return RandomVibAnalyzer(mock_bridge)

    @pytest.mark.asyncio
    async def test_grms_calculation(self, analyzer):
        """Compute gRMS from PSD profile."""
        psd_profile = [
            {"freq_hz": 20.0, "psd_g2hz": 0.01},
            {"freq_hz": 100.0, "psd_g2hz": 0.04},
            {"freq_hz": 2000.0, "psd_g2hz": 0.04},
        ]
        result = await analyzer.analyze(psd_profile)
        assert result.summary["grms"] > 0
        assert result.status == AnalysisStatus.PASS

    @pytest.mark.asyncio
    async def test_grms_exceeds_limit(self, analyzer):
        """gRMS above limit -> FAIL."""
        psd_profile = [
            {"freq_hz": 20.0, "psd_g2hz": 0.5},
            {"freq_hz": 2000.0, "psd_g2hz": 0.5},
        ]
        result = await analyzer.analyze(psd_profile, grms_limit=1.0)
        assert result.status == AnalysisStatus.FAIL

    @pytest.mark.asyncio
    async def test_miles_equation(self, analyzer):
        """Miles equation for SDOF response."""
        result = analyzer.miles_response(fn=100.0, q=10.0, psd_level=0.04)
        assert result > 0  # Should return positive gRMS

    @pytest.mark.asyncio
    async def test_empty_psd(self, analyzer):
        """Empty PSD profile -> WARNING."""
        result = await analyzer.analyze([])
        assert result.status == AnalysisStatus.WARN

    @pytest.mark.asyncio
    async def test_summary_fields(self, analyzer):
        """Summary contains expected fields."""
        psd_profile = [
            {"freq_hz": 20.0, "psd_g2hz": 0.01},
            {"freq_hz": 2000.0, "psd_g2hz": 0.04},
        ]
        result = await analyzer.analyze(psd_profile)
        assert "grms" in result.summary
        assert "freq_range" in result.summary
