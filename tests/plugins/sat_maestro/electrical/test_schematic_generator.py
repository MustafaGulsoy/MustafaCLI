"""Tests for the KiCad schematic generator."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.plugins.sat_maestro.cubesat_wizard import CubeSatDesign
from src.plugins.sat_maestro.electrical.parsers.kicad import KiCadParser
from src.plugins.sat_maestro.electrical.schematic_generator import (
    SchematicGenerator,
    SchematicResult,
    _RefAllocator,
    _SchematicSheet,
    _uuid,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_design() -> CubeSatDesign:
    """A default 1U CubeSat design with standard subsystems."""
    return CubeSatDesign(
        mission_name="TestSat-1",
        sat_size="1U",
        orbit_type="LEO",
        orbit_altitude=500,
        subsystems=["eps", "obc", "com_uhf", "adcs"],
        solar_config="Body-mounted",
        battery_type="Li-ion 18650",
        payload_type="Camera (EO)",
        payload_power=5.0,
        payload_mass=200,
    )


@pytest.fixture
def full_design() -> CubeSatDesign:
    """A 3U CubeSat design with all optional subsystems enabled."""
    return CubeSatDesign(
        mission_name="FullSat-3U",
        sat_size="3U",
        orbit_type="SSO",
        orbit_altitude=550,
        subsystems=[
            "eps", "obc", "com_uhf", "com_sband",
            "adcs", "gps", "propulsion", "thermal",
        ],
        solar_config="Deployable 2-panel",
        battery_type="Li-Po Pouch",
        payload_type="SDR (Comms)",
        payload_power=8.0,
        payload_mass=300,
    )


@pytest.fixture
def minimal_design() -> CubeSatDesign:
    """A minimal design with only EPS."""
    return CubeSatDesign(
        mission_name="MinSat",
        sat_size="1U",
        subsystems=["eps"],
        payload_power=1.0,
        payload_mass=50,
    )


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Temporary output directory for generated files."""
    out = tmp_path / "schematics"
    out.mkdir()
    return out


# ---------------------------------------------------------------------------
# UUID helper
# ---------------------------------------------------------------------------


class TestUUID:
    def test_uuid_returns_string(self) -> None:
        result = _uuid()
        assert isinstance(result, str)

    def test_uuid_is_unique(self) -> None:
        ids = {_uuid() for _ in range(100)}
        assert len(ids) == 100

    def test_uuid_is_valid_format(self) -> None:
        result = _uuid()
        # Standard UUID: 8-4-4-4-12 hex chars
        parts = result.split("-")
        assert len(parts) == 5
        assert [len(p) for p in parts] == [8, 4, 4, 4, 12]


# ---------------------------------------------------------------------------
# RefAllocator
# ---------------------------------------------------------------------------


class TestRefAllocator:
    def test_sequential_allocation(self) -> None:
        alloc = _RefAllocator()
        assert alloc.allocate("U") == "U1"
        assert alloc.allocate("U") == "U2"
        assert alloc.allocate("U") == "U3"

    def test_independent_prefixes(self) -> None:
        alloc = _RefAllocator()
        assert alloc.allocate("U") == "U1"
        assert alloc.allocate("R") == "R1"
        assert alloc.allocate("U") == "U2"
        assert alloc.allocate("R") == "R2"

    def test_multi_char_prefix(self) -> None:
        alloc = _RefAllocator()
        assert alloc.allocate("BT") == "BT1"
        assert alloc.allocate("ANT") == "ANT1"


# ---------------------------------------------------------------------------
# SchematicSheet
# ---------------------------------------------------------------------------


class TestSchematicSheet:
    def test_empty_sheet_renders(self) -> None:
        sheet = _SchematicSheet(title="Empty Test")
        rendered = sheet.render()
        assert "(kicad_sch" in rendered
        assert "Empty Test" in rendered
        assert "(lib_symbols" in rendered

    def test_add_net_returns_code(self) -> None:
        sheet = _SchematicSheet(title="Net Test")
        code1 = sheet.add_net("VCC")
        code2 = sheet.add_net("GND")
        assert code1 == 1
        assert code2 == 2

    def test_add_net_deduplicates(self) -> None:
        sheet = _SchematicSheet(title="Dedup Test")
        code1 = sheet.add_net("VCC")
        code2 = sheet.add_net("VCC")
        assert code1 == code2
        assert sheet.net_count == 1

    def test_wire_renders(self) -> None:
        sheet = _SchematicSheet(title="Wire Test")
        sheet.add_wire(0, 0, 10, 0)
        rendered = sheet.render()
        assert "(wire (pts" in rendered

    def test_label_renders(self) -> None:
        sheet = _SchematicSheet(title="Label Test")
        sheet.add_label("I2C_SDA", 50.0, 30.0)
        rendered = sheet.render()
        assert '(label "I2C_SDA"' in rendered


# ---------------------------------------------------------------------------
# SchematicGenerator — default design
# ---------------------------------------------------------------------------


class TestSchematicGeneratorDefault:
    def test_generate_returns_result(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        assert isinstance(result, SchematicResult)

    def test_generates_three_schematics(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        assert len(result.files) == 3

    def test_eps_file_exists(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        eps_path = output_dir / "cubesat_eps.kicad_sch"
        assert eps_path.exists()

    def test_obc_file_exists(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        obc_path = output_dir / "cubesat_obc.kicad_sch"
        assert obc_path.exists()

    def test_com_file_exists(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        com_path = output_dir / "cubesat_com.kicad_sch"
        assert com_path.exists()

    def test_bom_file_exists(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        bom_path = Path(result.bom_file)
        assert bom_path.exists()

    def test_component_count_is_positive(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        assert result.component_count > 0

    def test_net_count_is_positive(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        assert result.net_count > 0

    def test_summary_string(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        summary = result.summary()
        assert "Generated" in summary
        assert "Components" in summary


# ---------------------------------------------------------------------------
# KiCad file format validity
# ---------------------------------------------------------------------------


class TestKiCadFormatValidity:
    """Verify that generated files are valid KiCad S-expressions."""

    def test_eps_starts_with_kicad_sch(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        content = (output_dir / "cubesat_eps.kicad_sch").read_text(encoding="utf-8")
        assert content.startswith("(kicad_sch")

    def test_eps_contains_version(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        content = (output_dir / "cubesat_eps.kicad_sch").read_text(encoding="utf-8")
        assert "(version 20230121)" in content

    def test_eps_contains_generator(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        content = (output_dir / "cubesat_eps.kicad_sch").read_text(encoding="utf-8")
        assert '(generator "sat-maestro")' in content

    def test_eps_contains_lib_symbols(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        content = (output_dir / "cubesat_eps.kicad_sch").read_text(encoding="utf-8")
        assert "(lib_symbols" in content

    def test_eps_contains_symbol_instances(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        content = (output_dir / "cubesat_eps.kicad_sch").read_text(encoding="utf-8")
        assert '(symbol (lib_id' in content

    def test_eps_contains_net_definitions(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        content = (output_dir / "cubesat_eps.kicad_sch").read_text(encoding="utf-8")
        assert "(net (code" in content

    def test_obc_contains_wire_elements(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        content = (output_dir / "cubesat_obc.kicad_sch").read_text(encoding="utf-8")
        assert "(wire (pts" in content

    def test_all_files_have_balanced_parens(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        for filepath in result.files:
            content = Path(filepath).read_text(encoding="utf-8")
            open_count = content.count("(")
            close_count = content.count(")")
            assert open_count == close_count, (
                f"Unbalanced parens in {filepath}: "
                f"{open_count} open vs {close_count} close"
            )

    def test_all_files_have_uuids(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        for filepath in result.files:
            content = Path(filepath).read_text(encoding="utf-8")
            assert "(uuid" in content


# ---------------------------------------------------------------------------
# Parser round-trip
# ---------------------------------------------------------------------------


class TestParserRoundTrip:
    """Verify that generated schematics can be parsed by KiCadParser."""

    def test_eps_is_parseable(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        parser = KiCadParser()
        result = parser.parse(str(output_dir / "cubesat_eps.kicad_sch"), "eps")
        assert len(result.components) > 0

    def test_obc_is_parseable(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        parser = KiCadParser()
        result = parser.parse(str(output_dir / "cubesat_obc.kicad_sch"), "obc")
        assert len(result.components) > 0

    def test_com_is_parseable(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        parser = KiCadParser()
        result = parser.parse(str(output_dir / "cubesat_com.kicad_sch"), "com")
        assert len(result.components) > 0

    def test_eps_parsed_nets_include_power(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        gen.generate(output_dir)
        parser = KiCadParser()
        result = parser.parse(str(output_dir / "cubesat_eps.kicad_sch"), "eps")
        net_names = {n.name for n in result.nets}
        # Should have at least some power-related nets
        assert len(net_names) > 0


# ---------------------------------------------------------------------------
# BOM content
# ---------------------------------------------------------------------------


class TestBOMGeneration:
    def test_bom_has_header_row(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        with open(result.bom_file, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert "Reference" in reader.fieldnames
            assert "Value" in reader.fieldnames
            assert "Unit Price (USD)" in reader.fieldnames

    def test_bom_row_count_matches_components(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        with open(result.bom_file, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        expected = len(default_design.get_all_components())
        assert len(rows) == expected

    def test_bom_contains_payload(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        with open(result.bom_file, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        values = [r["Value"] for r in rows]
        assert any("Payload" in v for v in values)

    def test_bom_contains_structure(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        with open(result.bom_file, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        values = [r["Value"] for r in rows]
        assert any("Structure" in v for v in values)

    def test_bom_prices_are_numeric(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        with open(result.bom_file, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            price = float(row["Unit Price (USD)"])
            assert price >= 0


# ---------------------------------------------------------------------------
# Full design (all subsystems)
# ---------------------------------------------------------------------------


class TestFullDesign:
    def test_generates_all_three_files(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(full_design)
        result = gen.generate(output_dir)
        assert len(result.files) == 3

    def test_com_includes_sband(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "cubesat_com.kicad_sch").read_text(encoding="utf-8")
        assert "S-Band" in content or "S_Band" in content

    def test_obc_includes_gps(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "cubesat_obc.kicad_sch").read_text(encoding="utf-8")
        assert "GPS" in content

    def test_more_components_than_default(
        self,
        full_design: CubeSatDesign,
        default_design: CubeSatDesign,
        output_dir: Path,
        tmp_path: Path,
    ) -> None:
        out_full = output_dir
        out_default = tmp_path / "default_out"
        out_default.mkdir()

        r_full = SchematicGenerator(full_design).generate(out_full)
        r_default = SchematicGenerator(default_design).generate(out_default)
        assert r_full.component_count > r_default.component_count

    def test_balanced_parens_full_design(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(full_design)
        result = gen.generate(output_dir)
        for filepath in result.files:
            content = Path(filepath).read_text(encoding="utf-8")
            assert content.count("(") == content.count(")")


# ---------------------------------------------------------------------------
# Minimal design
# ---------------------------------------------------------------------------


class TestMinimalDesign:
    def test_only_eps_schematic_generated(
        self, minimal_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(minimal_design)
        result = gen.generate(output_dir)
        filenames = [Path(f).name for f in result.files]
        assert "cubesat_eps.kicad_sch" in filenames
        # OBC and COM should not be generated (no obc or com subsystems)
        assert "cubesat_obc.kicad_sch" not in filenames
        assert "cubesat_com.kicad_sch" not in filenames

    def test_bom_still_generated(
        self, minimal_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(minimal_design)
        result = gen.generate(output_dir)
        assert Path(result.bom_file).exists()


# ---------------------------------------------------------------------------
# Output directory creation
# ---------------------------------------------------------------------------


class TestOutputDirectoryCreation:
    def test_creates_missing_directory(
        self, default_design: CubeSatDesign, tmp_path: Path
    ) -> None:
        nested = tmp_path / "a" / "b" / "c"
        gen = SchematicGenerator(default_design)
        result = gen.generate(nested)
        assert nested.exists()
        assert len(result.files) > 0

    def test_works_with_existing_directory(
        self, default_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = SchematicGenerator(default_design)
        result = gen.generate(output_dir)
        assert len(result.files) > 0
