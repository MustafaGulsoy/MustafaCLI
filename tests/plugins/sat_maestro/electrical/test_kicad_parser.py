"""Tests for KiCad parser."""
import pytest
from pathlib import Path
from textwrap import dedent

from src.plugins.sat_maestro.electrical.parsers.kicad import KiCadParser


@pytest.fixture
def parser():
    return KiCadParser()


@pytest.fixture
def sample_schematic(tmp_path) -> Path:
    content = dedent("""\
    (kicad_sch (version 20230121)
      (symbol (lib_id "Device:R")
        (property "Reference" "R1"
          (at 0 0 0))
        (property "Value" "10k"
          (at 0 0 0))
        (pin passive line (at 0 0) (length 2.54)
          (name "1"))
        (pin passive line (at 0 0) (length 2.54)
          (name "2"))
      )
      (symbol (lib_id "MCU_ST:STM32F4")
        (property "Reference" "U1"
          (at 0 0 0))
        (property "Value" "STM32F407"
          (at 0 0 0))
        (pin power_in line (at 0 0) (length 2.54)
          (name "VCC"))
        (pin output line (at 0 0) (length 2.54)
          (name "PA0"))
      )
      (symbol (lib_id "Connector:Conn_01x04")
        (property "Reference" "J1"
          (at 0 0 0))
        (property "Value" "CONN_4"
          (at 0 0 0))
      )
      (net (code 1) (name "VCC_3V3"))
      (net (code 2) (name "GND"))
      (net (code 3) (name "SPI_MOSI"))
    )
    """)
    sch_file = tmp_path / "test.kicad_sch"
    sch_file.write_text(content)
    return sch_file


@pytest.fixture
def sample_pcb(tmp_path) -> Path:
    content = dedent("""\
    (kicad_pcb (version 20221018)
      (footprint "Resistor_SMD:R_0402"
        (fp_text reference "R1" (at 0 0))
      )
      (footprint "Package_QFP:LQFP-64"
        (fp_text reference "U1" (at 0 0))
      )
      (net 0 "")
      (net 1 "VCC_3V3")
      (net 2 "GND")
    )
    """)
    pcb_file = tmp_path / "test.kicad_pcb"
    pcb_file.write_text(content)
    return pcb_file


class TestKiCadParser:
    def test_parse_schematic_components(self, parser, sample_schematic):
        result = parser.parse(str(sample_schematic), subsystem="EPS")
        assert len(result.components) == 3
        refs = [c.properties["reference"] for c in result.components]
        assert "R1" in refs
        assert "U1" in refs
        assert "J1" in refs

    def test_parse_schematic_types(self, parser, sample_schematic):
        result = parser.parse(str(sample_schematic), subsystem="EPS")
        from src.plugins.sat_maestro.core.graph_models import ComponentType
        type_map = {c.properties["reference"]: c.type for c in result.components}
        assert type_map["R1"] == ComponentType.PASSIVE
        assert type_map["U1"] == ComponentType.IC
        assert type_map["J1"] == ComponentType.CONNECTOR

    def test_parse_schematic_nets(self, parser, sample_schematic):
        result = parser.parse(str(sample_schematic), subsystem="EPS")
        assert len(result.nets) == 3
        from src.plugins.sat_maestro.core.graph_models import NetType
        net_types = {n.name: n.type for n in result.nets}
        assert net_types["VCC_3V3"] == NetType.POWER
        assert net_types["GND"] == NetType.GROUND
        assert net_types["SPI_MOSI"] == NetType.SIGNAL

    def test_parse_schematic_pins(self, parser, sample_schematic):
        result = parser.parse(str(sample_schematic), subsystem="EPS")
        # R1 has 2 pins, U1 has 2 pins
        assert len(result.pins) >= 4

    def test_parse_pcb(self, parser, sample_pcb):
        result = parser.parse(str(sample_pcb), subsystem="EPS")
        assert len(result.components) == 2
        assert len(result.nets) >= 2

    def test_file_not_found(self, parser):
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/file.kicad_sch")

    def test_unsupported_extension(self, parser, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported"):
            parser.parse(str(f))

    def test_subsystem_in_ids(self, parser, sample_schematic):
        result = parser.parse(str(sample_schematic), subsystem="OBC")
        for comp in result.components:
            assert comp.id.startswith("OBC_")
            assert comp.subsystem == "OBC"
