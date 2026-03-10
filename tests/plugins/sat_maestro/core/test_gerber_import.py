"""Tests for Gerber -> Neo4j import and Neo4j deep links."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.graph_ops import GraphOperations
from src.plugins.sat_maestro.core.report import ReportFormat, ReportGenerator
from src.plugins.sat_maestro.core.graph_models import AnalysisResult, AnalysisStatus
from src.plugins.sat_maestro.config import SatMaestroConfig


class TestGerberImport:
    @pytest.mark.asyncio
    async def test_create_pad(self, graph_ops):
        graph_ops._client.execute_write = AsyncMock(return_value=[{"id": "pad_1"}])

        class FakePad:
            id = "pad_1"
            x = 1.0
            y = 2.0
            aperture = "D10"
            layer = "Top Copper"
            net_name = "VCC"

        result = await graph_ops.create_pad(FakePad())
        assert result == "pad_1"
        graph_ops._client.execute_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_trace(self, graph_ops):
        graph_ops._client.execute_write = AsyncMock(return_value=[{"id": "trace_1"}])

        class FakeTrace:
            id = "trace_1"
            start_x = 0.0
            start_y = 0.0
            end_x = 1.0
            end_y = 1.0
            width = 0.01
            layer = "Top Copper"
            net_name = ""

        result = await graph_ops.create_trace(FakeTrace())
        assert result == "trace_1"

    @pytest.mark.asyncio
    async def test_pcb_stats(self, graph_ops):
        graph_ops._client.execute = AsyncMock(side_effect=[
            [{"count": 42}],
            [{"count": 15}],
        ])
        stats = await graph_ops.get_pcb_stats()
        assert stats["pads"] == 42
        assert stats["traces"] == 15


class TestNeo4jDeepLinks:
    @pytest.mark.asyncio
    async def test_neo4j_report_format(self, tmp_path):
        config = SatMaestroConfig(report_output_dir=str(tmp_path))
        gen = ReportGenerator(config)
        results = [
            AnalysisResult(analyzer="pin_to_pin", status=AnalysisStatus.PASS, summary={}),
        ]
        output = await gen.generate(results, ReportFormat.NEO4J, run_id="test-001")
        assert "Neo4j Browser" in output or "neo4j" in output.lower()
        assert "test-001" in output
        assert "Cypher" in output or "MATCH" in output

    @pytest.mark.asyncio
    async def test_html_has_neo4j_section(self, tmp_path):
        config = SatMaestroConfig(report_output_dir=str(tmp_path))
        gen = ReportGenerator(config)
        results = [
            AnalysisResult(analyzer="test", status=AnalysisStatus.PASS, summary={}),
        ]
        path = await gen.generate(results, ReportFormat.HTML, str(tmp_path))
        from pathlib import Path
        html = Path(path).read_text()
        assert "Neo4j" in html
        assert "localhost:7474" in html
