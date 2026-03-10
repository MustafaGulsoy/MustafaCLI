"""Tests for report generator."""
import json
import pytest
from pathlib import Path

from src.plugins.sat_maestro.config import SatMaestroConfig
from src.plugins.sat_maestro.core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from src.plugins.sat_maestro.core.report import ReportFormat, ReportGenerator


@pytest.fixture
def config(tmp_path):
    return SatMaestroConfig(report_output_dir=str(tmp_path))


@pytest.fixture
def generator(config):
    return ReportGenerator(config)


@pytest.fixture
def sample_results():
    return [
        AnalysisResult(
            analyzer="pin_to_pin",
            status=AnalysisStatus.PASS,
            summary={"connections_checked": 42, "open_circuits": 0},
        ),
        AnalysisResult(
            analyzer="power_budget",
            status=AnalysisStatus.WARN,
            violations=[
                Violation(
                    rule_id="POWER-MARGIN",
                    severity=Severity.WARNING,
                    message="Rail 3V3: margin 15%",
                    component_path="REG1/VOUT",
                ),
            ],
            summary={"rails_analyzed": 3, "overall_margin": 0.15},
        ),
        AnalysisResult(
            analyzer="connector",
            status=AnalysisStatus.FAIL,
            violations=[
                Violation(
                    rule_id="ECSS-E-ST-20C-5.3.1",
                    severity=Severity.ERROR,
                    message="Connector J4 exceeds 75% derating",
                    component_path="J4",
                ),
            ],
            summary={"mate_pairs": 5},
        ),
    ]


class TestReportGenerator:
    @pytest.mark.asyncio
    async def test_cli_report(self, generator, sample_results):
        output = await generator.generate(sample_results, ReportFormat.CLI)
        assert "SAT-MAESTRO" in output
        assert "FAIL" in output
        assert "ECSS-E-ST-20C-5.3.1" in output
        assert "J4" in output

    @pytest.mark.asyncio
    async def test_json_report(self, generator, sample_results, tmp_path):
        path = await generator.generate(sample_results, ReportFormat.JSON, str(tmp_path))
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["status"] == "FAIL"
        assert data["exit_code"] == 1
        assert len(data["violations"]) == 2
        assert "pin_to_pin" in data["analyzers"]

    @pytest.mark.asyncio
    async def test_html_report(self, generator, sample_results, tmp_path):
        path = await generator.generate(sample_results, ReportFormat.HTML, str(tmp_path))
        assert Path(path).exists()
        html = Path(path).read_text()
        assert "SAT-MAESTRO" in html
        assert "FAIL" in html

    @pytest.mark.asyncio
    async def test_all_formats(self, generator, sample_results, tmp_path):
        output = await generator.generate(sample_results, ReportFormat.ALL, str(tmp_path))
        # CLI report is multiline, then JSON path, then HTML path
        assert "SAT-MAESTRO" in output  # CLI part
        assert ".json" in output
        assert ".html" in output

    @pytest.mark.asyncio
    async def test_string_format(self, generator, sample_results):
        output = await generator.generate(sample_results, "cli")
        assert "SAT-MAESTRO" in output

    @pytest.mark.asyncio
    async def test_pass_status(self, generator):
        results = [
            AnalysisResult(analyzer="test", status=AnalysisStatus.PASS, summary={}),
        ]
        output = await generator.generate(results, ReportFormat.CLI)
        assert "PASS" in output

    @pytest.mark.asyncio
    async def test_summarize_pin_to_pin(self, generator):
        r = AnalysisResult(
            analyzer="pin_to_pin",
            status=AnalysisStatus.PASS,
            summary={"connections_checked": 100, "open_circuits": 0},
        )
        summary = generator._summarize_result(r)
        assert "100/100" in summary

    @pytest.mark.asyncio
    async def test_summarize_power_budget(self, generator):
        r = AnalysisResult(
            analyzer="power_budget",
            status=AnalysisStatus.PASS,
            summary={"rails_analyzed": 5, "overall_margin": 0.30},
        )
        summary = generator._summarize_result(r)
        assert "5 rails" in summary
