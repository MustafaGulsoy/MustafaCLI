"""Tests for Gerber parser."""
import pytest
from pathlib import Path
from textwrap import dedent

from src.plugins.sat_maestro.electrical.parsers.gerber import GerberParser


@pytest.fixture
def parser():
    return GerberParser()


@pytest.fixture
def sample_gerber(tmp_path) -> Path:
    content = dedent("""\
    G04 Test Gerber*
    %FSLAX24Y24*%
    %MOIN*%
    %ADD10C,0.010*%
    %ADD11R,0.060X0.060*%
    D10*
    X10000Y20000D02*
    X30000Y20000D01*
    X50000Y40000D01*
    D11*
    X10000Y10000D03*
    X30000Y10000D03*
    X50000Y10000D03*
    M02*
    """)
    gerber_file = tmp_path / "test.gtl"
    gerber_file.write_text(content)
    return gerber_file


class TestGerberParser:
    def test_parse_apertures(self, parser, sample_gerber):
        result = parser.parse(str(sample_gerber))
        assert "D10" in result.apertures
        assert "D11" in result.apertures
        assert result.apertures["D10"]["shape"] == "C"
        assert result.apertures["D11"]["shape"] == "R"

    def test_parse_pads(self, parser, sample_gerber):
        result = parser.parse(str(sample_gerber))
        assert len(result.pads) == 3  # Three D03 flash commands

    def test_parse_traces(self, parser, sample_gerber):
        result = parser.parse(str(sample_gerber))
        assert len(result.traces) == 2  # Two D01 draw commands

    def test_trace_width(self, parser, sample_gerber):
        result = parser.parse(str(sample_gerber))
        # D10 is circular with 0.010 diameter
        for trace in result.traces:
            assert trace.width == pytest.approx(0.010, abs=0.001)

    def test_file_not_found(self, parser):
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/file.gbr")

    def test_parse_directory(self, parser, tmp_path):
        for ext in [".gtl", ".gbl", ".gts"]:
            f = tmp_path / f"board{ext}"
            f.write_text("%FSLAX24Y24*%\nM02*\n")
        results = parser.parse_directory(str(tmp_path))
        assert len(results) == 3

    def test_detect_layers(self, parser, tmp_path):
        for ext, expected_layer in [(".gtl", "Top Copper"), (".gbl", "Bottom Copper")]:
            f = tmp_path / f"board{ext}"
            f.write_text("%FSLAX24Y24*%\nM02*\n")
        results = parser.parse_directory(str(tmp_path))
        layers = [r.layers[0] for r in results]
        assert "Top Copper" in layers
        assert "Bottom Copper" in layers

    def test_source_file_recorded(self, parser, sample_gerber):
        result = parser.parse(str(sample_gerber))
        assert result.source_file == str(sample_gerber)
