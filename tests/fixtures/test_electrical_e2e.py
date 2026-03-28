"""End-to-end tests for the SAT-MAESTRO electrical analysis parsing pipeline.

Tests KiCad schematic and Gerber RS-274X parsing without requiring Neo4j.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is on the import path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.plugins.sat_maestro.electrical.parsers.kicad import KiCadParser, ParseResult
from src.plugins.sat_maestro.electrical.parsers.gerber import GerberParser, GerberResult
from src.plugins.sat_maestro.core.graph_models import ComponentType, NetType, PinDirection

FIXTURES_DIR = Path(__file__).resolve().parent


# ── KiCad schematic parsing ──────────────────────────────────────────────────


class TestKiCadParserE2E:
    """End-to-end tests for KiCad schematic parsing."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.parser = KiCadParser()
        self.fixture = str(FIXTURES_DIR / "cubesat_eps.kicad_sch")

    def test_parse_returns_parse_result(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        assert isinstance(result, ParseResult)
        assert result.source_file == self.fixture

    def test_all_components_extracted(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        refs = {c.properties["reference"] for c in result.components}
        assert refs == {"J1", "U1", "U2"}

    def test_component_types(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        by_ref = {c.properties["reference"]: c for c in result.components}
        assert by_ref["J1"].type == ComponentType.CONNECTOR
        assert by_ref["U1"].type == ComponentType.IC
        assert by_ref["U2"].type == ComponentType.IC

    def test_component_values(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        by_ref = {c.properties["reference"]: c for c in result.components}
        assert by_ref["U1"].properties["value"] == "BQ25570"
        assert by_ref["U2"].properties["value"] == "TPS62A02_3V3"
        assert by_ref["J1"].properties["value"] == "SolarPanel_Input"

    def test_component_ids_contain_subsystem(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        for comp in result.components:
            assert comp.id.startswith("eps_"), f"Expected eps_ prefix on {comp.id}"

    def test_pins_extracted(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        assert len(result.pins) >= 4, "J1 alone has 4 pins"

    def test_pin_names(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        pin_names = {p.name for p in result.pins}
        # Solar panel connector pins
        assert "VSOLAR_P" in pin_names
        assert "VSOLAR_N" in pin_names
        # BQ25570 pins
        assert "VIN_DC" in pin_names
        assert "VBAT" in pin_names
        # Regulator pins
        assert "VOUT" in pin_names
        assert "EN" in pin_names

    def test_pin_directions(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        by_name = {p.name: p for p in result.pins}
        # power_in maps to POWER
        assert by_name["VSOLAR_P"].direction == PinDirection.POWER
        # input maps to INPUT
        assert by_name["VIN_DC"].direction == PinDirection.INPUT
        # output maps to OUTPUT
        assert by_name["VBAT"].direction == PinDirection.OUTPUT

    def test_pins_reference_valid_components(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        comp_ids = {c.id for c in result.components}
        for pin in result.pins:
            assert pin.component_id in comp_ids, (
                f"Pin {pin.name} references unknown component {pin.component_id}"
            )

    def test_all_nets_extracted(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        net_names = {n.name for n in result.nets}
        assert net_names == {"VSOLAR", "VBATT", "3V3", "GND", "MPPT_REF", "TEMP_SENSE"}

    def test_net_types(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        by_name = {n.name: n for n in result.nets}
        assert by_name["3V3"].type == NetType.POWER
        assert by_name["GND"].type == NetType.GROUND
        assert by_name["MPPT_REF"].type == NetType.SIGNAL
        assert by_name["TEMP_SENSE"].type == NetType.SIGNAL

    def test_signal_nets_present(self):
        result = self.parser.parse(self.fixture, subsystem="eps")
        signal_nets = [n for n in result.nets if n.type == NetType.SIGNAL]
        assert len(signal_nets) >= 2, "Expected at least 2 signal nets"


# ── Gerber RS-274X parsing ───────────────────────────────────────────────────


class TestGerberParserE2E:
    """End-to-end tests for Gerber RS-274X parsing."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.parser = GerberParser()
        self.fixture = str(FIXTURES_DIR / "cubesat_eps.gbr")

    def test_parse_returns_gerber_result(self):
        result = self.parser.parse(self.fixture)
        assert isinstance(result, GerberResult)
        assert result.source_file == self.fixture

    def test_apertures_extracted(self):
        result = self.parser.parse(self.fixture)
        assert "D10" in result.apertures
        assert "D11" in result.apertures
        assert "D12" in result.apertures

    def test_aperture_shapes(self):
        result = self.parser.parse(self.fixture)
        assert result.apertures["D10"]["shape"] == "C"  # circle
        assert result.apertures["D11"]["shape"] == "R"  # rectangle
        assert result.apertures["D12"]["shape"] == "C"  # circle

    def test_aperture_params(self):
        result = self.parser.parse(self.fixture)
        assert result.apertures["D10"]["params"] == "0.0100"
        assert result.apertures["D11"]["params"] == "0.0600X0.0600"

    def test_pads_extracted(self):
        result = self.parser.parse(self.fixture)
        # D11 flashes: 4 (J1 pins) + D12 flashes: 3 (IC pads) = 7 pads
        assert len(result.pads) == 7

    def test_pad_coordinates(self):
        result = self.parser.parse(self.fixture)
        # First pad: X10000Y10000 with 2.4 format => 1.0, 1.0
        first = result.pads[0]
        assert abs(first.x - 1.0) < 1e-6
        assert abs(first.y - 1.0) < 1e-6

    def test_pad_apertures(self):
        result = self.parser.parse(self.fixture)
        d11_pads = [p for p in result.pads if p.aperture == "D11"]
        d12_pads = [p for p in result.pads if p.aperture == "D12"]
        assert len(d11_pads) == 4
        assert len(d12_pads) == 3

    def test_traces_extracted(self):
        result = self.parser.parse(self.fixture)
        assert len(result.traces) == 3

    def test_trace_widths(self):
        result = self.parser.parse(self.fixture)
        # All traces drawn with D10 (circle 0.0100)
        for trace in result.traces:
            assert abs(trace.width - 0.01) < 1e-6

    def test_trace_coordinates(self):
        result = self.parser.parse(self.fixture)
        # First trace: from (1.0, 1.0) to (3.0, 1.0)
        t = result.traces[0]
        assert abs(t.start_x - 1.0) < 1e-6
        assert abs(t.start_y - 1.0) < 1e-6
        assert abs(t.end_x - 3.0) < 1e-6
        assert abs(t.end_y - 1.0) < 1e-6

    def test_no_warnings(self):
        result = self.parser.parse(self.fixture)
        assert result.warnings == []


# ── Combined pipeline test ───────────────────────────────────────────────────


class TestElectricalPipelineE2E:
    """Verify both parsers work together on the EPS fixture set."""

    def test_full_pipeline(self):
        kicad = KiCadParser()
        gerber = GerberParser()

        sch = kicad.parse(str(FIXTURES_DIR / "cubesat_eps.kicad_sch"), subsystem="eps")
        pcb = gerber.parse(str(FIXTURES_DIR / "cubesat_eps.gbr"))

        # Schematic produced components, pins, nets
        assert len(sch.components) > 0
        assert len(sch.pins) > 0
        assert len(sch.nets) > 0

        # Gerber produced pads, traces, apertures
        assert len(pcb.pads) > 0
        assert len(pcb.traces) > 0
        assert len(pcb.apertures) > 0

        # Cross-check: schematic connector pin count matches gerber pad group
        j1_pins = [p for p in sch.pins if p.component_id == "eps_J1"]
        d11_pads = [p for p in pcb.pads if p.aperture == "D11"]
        assert len(j1_pins) == len(d11_pads), (
            "J1 connector pin count should match D11 pad count"
        )
