"""KiCad schematic generator for CubeSat auto-design pipeline.

Generates valid KiCad 6/7 schematic (.kicad_sch) files from a CubeSatDesign,
producing separate schematics for EPS, OBC, and COM subsystems along with a
consolidated Bill of Materials (BOM) in CSV format.

The output files are parseable by :class:`KiCadParser` and can be opened
directly in KiCad EESchema.
"""
from __future__ import annotations

import csv
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..bus_generator import BUS_RULES, PIN_TEMPLATES
from ..cubesat_wizard import COMPONENT_CATALOG, CubeSatDesign

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KICAD_VERSION = 20230121
_GENERATOR = "sat-maestro"

# Grid spacing for component placement (in KiCad mils -> 2.54mm units)
_GRID_X = 50.0  # horizontal spacing between components
_GRID_Y = 40.0  # vertical spacing between rows
_ORIGIN_X = 30.0  # left margin
_ORIGIN_Y = 30.0  # top margin
_PIN_LENGTH = 2.54
_WIRE_EXTENSION = 10.0  # length of stub wires from pins

# KiCad pin direction keywords
_PIN_DIR_KICAD: dict[str, str] = {
    "INPUT": "input",
    "OUTPUT": "output",
    "BIDIRECTIONAL": "bidirectional",
    "POWER": "power_in",
}

# Estimated pricing and packaging for BOM generation
_BOM_ESTIMATES: dict[str, dict[str, Any]] = {
    "eps_pcu": {
        "package": "Custom PCB Module",
        "supplier": "GomSpace / Endurosat",
        "unit_price": 2500.0,
    },
    "eps_batt": {
        "package": "18650 Pack",
        "supplier": "EaglePicher / SAFT",
        "unit_price": 1200.0,
    },
    "eps_solar": {
        "package": "GaAs Panel",
        "supplier": "SpectroLab / AzurSpace",
        "unit_price": 3500.0,
    },
    "obc_main": {
        "package": "PC/104 Module",
        "supplier": "ISIS / NanoAvionics",
        "unit_price": 4000.0,
    },
    "com_uhf_trx": {
        "package": "PCB Module",
        "supplier": "ISIS / Endurosat",
        "unit_price": 3000.0,
    },
    "com_uhf_ant": {
        "package": "Deployable Monopole",
        "supplier": "ISIS / Innovative Solutions",
        "unit_price": 1500.0,
    },
    "com_sband_tx": {
        "package": "PCB Module",
        "supplier": "Endurosat / IQ Spacecom",
        "unit_price": 5000.0,
    },
    "com_sband_ant": {
        "package": "Patch Antenna",
        "supplier": "Endurosat / Anywaves",
        "unit_price": 800.0,
    },
    "adcs_unit": {
        "package": "Integrated Module",
        "supplier": "CubeSpace / NewSpace Systems",
        "unit_price": 8000.0,
    },
    "gps_rx": {
        "package": "PCB Module",
        "supplier": "SkyFox Labs / NovAtel",
        "unit_price": 1000.0,
    },
    "prop_unit": {
        "package": "Thruster Module",
        "supplier": "Enpulsion / ThrustMe",
        "unit_price": 15000.0,
    },
    "therm_heater": {
        "package": "Kapton Heater",
        "supplier": "Minco / Omega",
        "unit_price": 150.0,
    },
    "payload_main": {
        "package": "Custom Module",
        "supplier": "Mission-specific",
        "unit_price": 5000.0,
    },
    "structure_frame": {
        "package": "Al-7075 Machined",
        "supplier": "ISIS / Pumpkin",
        "unit_price": 3000.0,
    },
}

# Subsystem-to-schematic mapping: which component IDs go into which file
_EPS_COMPONENTS = {"eps_pcu", "eps_batt", "eps_solar"}
_OBC_COMPONENTS = {"obc_main", "adcs_unit", "gps_rx", "prop_unit", "therm_heater", "payload_main"}
_COM_COMPONENTS = {"com_uhf_trx", "com_uhf_ant", "com_sband_tx", "com_sband_ant"}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SchematicResult:
    """Result of schematic generation."""

    files: list[str] = field(default_factory=list)
    bom_file: str = ""
    component_count: int = 0
    net_count: int = 0

    def summary(self) -> str:
        """Return a human-readable summary of the generation result."""
        lines = [
            f"Generated {len(self.files)} schematic files:",
            *[f"  - {f}" for f in self.files],
            f"  - {self.bom_file}",
            f"Components: {self.component_count}, Nets: {self.net_count}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers — S-expression builders
# ---------------------------------------------------------------------------

def _uuid() -> str:
    """Generate a KiCad-compatible UUID string."""
    return str(uuid.uuid4())


def _sexpr_property(
    key: str,
    value: str,
    prop_id: int,
    x: float,
    y: float,
    *,
    font_size: float = 1.27,
    hide: bool = False,
) -> str:
    """Build a KiCad property S-expression."""
    hide_str = " hide" if hide else ""
    return (
        f'    (property "{key}" "{value}" (at {x:.2f} {y:.2f} 0) '
        f"(effects (font (size {font_size} {font_size})){hide_str}))"
    )


def _sexpr_pin(
    pin_name: str,
    direction: str,
    x: float,
    y: float,
    *,
    pin_number: str = "",
    length: float = _PIN_LENGTH,
) -> str:
    """Build a KiCad pin S-expression."""
    kicad_dir = _PIN_DIR_KICAD.get(direction, "bidirectional")
    number = pin_number or pin_name
    return (
        f'      (pin {kicad_dir} line (at {x:.2f} {y:.2f} 0) '
        f'(length {length}) (name "{pin_name}") (number "{number}"))'
    )


@dataclass
class _PlacedComponent:
    """Internal record of a component placed on a schematic sheet."""

    comp_id: str
    name: str
    reference: str
    lib_id: str
    x: float
    y: float
    pins: list[dict[str, Any]]
    uuid: str = field(default_factory=_uuid)
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class _PlacedWire:
    """A wire segment between two points."""

    x1: float
    y1: float
    x2: float
    y2: float
    uuid: str = field(default_factory=_uuid)


@dataclass
class _PlacedLabel:
    """A net label at a specific position."""

    name: str
    x: float
    y: float
    uuid: str = field(default_factory=_uuid)


@dataclass
class _PlacedNet:
    """A net definition with code and name."""

    code: int
    name: str


# ---------------------------------------------------------------------------
# Schematic sheet builder
# ---------------------------------------------------------------------------

class _SchematicSheet:
    """Builds a single .kicad_sch file from placed elements."""

    def __init__(self, title: str) -> None:
        self.title = title
        self._components: list[_PlacedComponent] = []
        self._wires: list[_PlacedWire] = []
        self._labels: list[_PlacedLabel] = []
        self._nets: list[_PlacedNet] = []
        self._net_counter = 0

    def add_component(self, comp: _PlacedComponent) -> None:
        self._components.append(comp)

    def add_wire(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self._wires.append(_PlacedWire(x1=x1, y1=y1, x2=x2, y2=y2))

    def add_label(self, name: str, x: float, y: float) -> None:
        self._labels.append(_PlacedLabel(name=name, x=x, y=y))

    def add_net(self, name: str) -> int:
        """Register a net and return its code number."""
        # Check for existing net with same name
        for net in self._nets:
            if net.name == name:
                return net.code
        self._net_counter += 1
        self._nets.append(_PlacedNet(code=self._net_counter, name=name))
        return self._net_counter

    @property
    def component_count(self) -> int:
        return len(self._components)

    @property
    def net_count(self) -> int:
        return len(self._nets)

    def render(self) -> str:
        """Render the complete .kicad_sch S-expression string."""
        parts: list[str] = []
        parts.append(
            f"(kicad_sch (version {_KICAD_VERSION}) "
            f'(generator "{_GENERATOR}")'
        )
        parts.append("")

        # Title block
        parts.append(f'  (title_block (title "{self.title}"))')
        parts.append("")

        # Lib symbols section — define the symbol shapes in the library
        parts.append("  (lib_symbols")
        for comp in self._components:
            parts.append(self._render_lib_symbol(comp))
        parts.append("  )")
        parts.append("")

        # Symbol instances — placed on the sheet
        for comp in self._components:
            parts.append(self._render_symbol_instance(comp))
            parts.append("")

        # Wires
        for wire in self._wires:
            parts.append(
                f"  (wire (pts (xy {wire.x1:.2f} {wire.y1:.2f}) "
                f"(xy {wire.x2:.2f} {wire.y2:.2f})) "
                f'(uuid "{wire.uuid}"))'
            )

        if self._wires:
            parts.append("")

        # Labels
        for label in self._labels:
            parts.append(
                f'  (label "{label.name}" (at {label.x:.2f} {label.y:.2f} 0) '
                f"(effects (font (size 1.27 1.27))) "
                f'(uuid "{label.uuid}"))'
            )

        if self._labels:
            parts.append("")

        # Net definitions
        for net in self._nets:
            parts.append(
                f'  (net (code {net.code}) (name "{net.name}"))'
            )

        if self._nets:
            parts.append("")

        parts.append(")")
        parts.append("")
        return "\n".join(parts)

    def _render_lib_symbol(self, comp: _PlacedComponent) -> str:
        """Render a lib_symbols entry for a component."""
        lines: list[str] = []
        lib_name = comp.lib_id
        lines.append(f'    (symbol "{lib_name}"')
        lines.append(f'      (in_bom yes) (on_board yes)')

        # Sub-symbol unit 1
        lines.append(f'      (symbol "{lib_name}_1_1"')

        # Draw a simple rectangle body
        pin_count = len(comp.pins)
        body_h = max(pin_count * _PIN_LENGTH, 10.0)
        half_h = body_h / 2.0
        body_w = 15.0
        half_w = body_w / 2.0

        lines.append(
            f"        (rectangle (start {-half_w:.2f} {-half_h:.2f}) "
            f"(end {half_w:.2f} {half_h:.2f}) "
            f"(stroke (width 0.254) (type default)) "
            f"(fill (type background)))"
        )

        # Pins — inputs on the left, outputs on the right
        pin_y_start = half_h - _PIN_LENGTH
        left_pins = [
            p for p in comp.pins
            if p.get("direction", "") in ("INPUT", "POWER", "BIDIRECTIONAL")
        ]
        right_pins = [
            p for p in comp.pins
            if p.get("direction", "") == "OUTPUT"
        ]
        # Anything not yet assigned goes to left
        assigned_names = {p["name"] for p in left_pins} | {p["name"] for p in right_pins}
        for p in comp.pins:
            if p["name"] not in assigned_names:
                left_pins.append(p)

        pin_num = 1
        for i, pin in enumerate(left_pins):
            py = pin_y_start - i * _PIN_LENGTH * 1.5
            lines.append(
                _sexpr_pin(
                    pin["name"],
                    pin.get("direction", "BIDIRECTIONAL"),
                    -(half_w + _PIN_LENGTH),
                    py,
                    pin_number=str(pin_num),
                )
            )
            pin_num += 1

        for i, pin in enumerate(right_pins):
            py = pin_y_start - i * _PIN_LENGTH * 1.5
            lines.append(
                _sexpr_pin(
                    pin["name"],
                    pin.get("direction", "OUTPUT"),
                    half_w + _PIN_LENGTH,
                    py,
                    pin_number=str(pin_num),
                )
            )
            pin_num += 1

        lines.append("      )")  # close symbol unit
        lines.append("    )")  # close symbol
        return "\n".join(lines)

    def _render_symbol_instance(self, comp: _PlacedComponent) -> str:
        """Render a placed symbol instance on the sheet."""
        lines: list[str] = []
        lines.append(
            f'  (symbol (lib_id "{comp.lib_id}") '
            f"(at {comp.x:.2f} {comp.y:.2f} 0) "
            f"(unit 1)"
        )
        lines.append(f'    (uuid "{comp.uuid}")')

        # Properties: Reference, Value, Footprint, Datasheet
        prop_y = comp.y - 3.0
        lines.append(
            _sexpr_property("Reference", comp.reference, 0, comp.x, prop_y)
        )
        lines.append(
            _sexpr_property(
                "Value", comp.name, 1, comp.x, prop_y - 2.54
            )
        )
        pkg = comp.properties.get("package", "")
        lines.append(
            _sexpr_property(
                "Footprint", pkg, 2, comp.x, prop_y - 5.08, hide=True
            )
        )
        lines.append(
            _sexpr_property("Datasheet", "", 3, comp.x, prop_y - 7.62, hide=True)
        )

        # Pin instances with UUIDs (for KiCad 7 compatibility)
        for pin in comp.pins:
            pin_uuid = _uuid()
            lines.append(
                f'    (pin "{pin.get("number", pin["name"])}" '
                f'(uuid "{pin_uuid}"))'
            )

        lines.append("  )")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reference designator allocator
# ---------------------------------------------------------------------------

class _RefAllocator:
    """Allocates unique reference designators per prefix across all sheets."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def allocate(self, prefix: str) -> str:
        """Return the next reference designator for a given prefix (e.g. 'U' -> 'U1')."""
        count = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = count
        return f"{prefix}{count}"


# ---------------------------------------------------------------------------
# Main generator class
# ---------------------------------------------------------------------------

class SchematicGenerator:
    """Generate KiCad 6/7 schematics from a CubeSatDesign.

    Produces three schematic files (EPS, OBC, COM) and a BOM CSV.

    Args:
        design: The CubeSat design containing subsystem selections.
    """

    def __init__(self, design: CubeSatDesign) -> None:
        self._design = design
        self._ref_alloc = _RefAllocator()
        self._all_placed: dict[str, _PlacedComponent] = {}
        self._result = SchematicResult()

    def generate(self, output_dir: Path) -> SchematicResult:
        """Generate all schematic files and BOM into *output_dir*.

        Args:
            output_dir: Directory to write generated files into.
                        Created if it does not exist.

        Returns:
            A :class:`SchematicResult` describing the generated artefacts.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        active_ids = {c["id"] for c in self._design.get_all_components()}

        logger.info(
            "Generating schematics for %s (%d components)",
            self._design.mission_name,
            len(active_ids),
        )

        # Generate each sheet
        eps_path = self._generate_eps_schematic(output_dir, active_ids)
        obc_path = self._generate_obc_schematic(output_dir, active_ids)
        com_path = self._generate_com_schematic(output_dir, active_ids)

        for p in (eps_path, obc_path, com_path):
            if p is not None:
                self._result.files.append(str(p))

        # BOM
        bom_path = self._generate_bom(output_dir, active_ids)
        self._result.bom_file = str(bom_path)

        # Totals
        self._result.component_count = len(self._all_placed)

        logger.info(
            "Schematic generation complete: %d files, %d components, %d nets",
            len(self._result.files),
            self._result.component_count,
            self._result.net_count,
        )
        return self._result

    # ------------------------------------------------------------------
    # EPS schematic
    # ------------------------------------------------------------------

    def _generate_eps_schematic(
        self, output_dir: Path, active_ids: set[str]
    ) -> Path | None:
        """Generate the EPS power-system schematic."""
        sheet = _SchematicSheet(
            title=f"{self._design.mission_name} — EPS Power System"
        )

        # Determine which EPS components are active
        eps_ids = _EPS_COMPONENTS & active_ids
        if not eps_ids:
            logger.info("No EPS components selected; skipping EPS schematic")
            return None

        # Also include load summaries as power flags
        load_ids = active_ids - _EPS_COMPONENTS - {"structure_frame"}

        # --- Place EPS components in a left-to-right power flow ---
        # Row 0: Solar -> Charger/PCU -> Battery
        flow_order = ["eps_solar", "eps_pcu", "eps_batt"]
        col = 0
        for comp_id in flow_order:
            if comp_id not in eps_ids:
                continue
            placed = self._place_component(
                comp_id, sheet, _ORIGIN_X + col * _GRID_X, _ORIGIN_Y
            )
            if placed is not None:
                col += 1

        # Row 1: Load subsystem power flags — one per load for net label stubs
        col = 0
        for comp_id in sorted(load_ids):
            placed = self._place_component(
                comp_id,
                sheet,
                _ORIGIN_X + col * _GRID_X,
                _ORIGIN_Y + _GRID_Y,
            )
            if placed is not None:
                col += 1

        # --- Add nets and wires ---
        self._add_bus_connections(sheet, active_ids, target_comp_ids=eps_ids | load_ids)

        # Write file
        path = output_dir / "cubesat_eps.kicad_sch"
        path.write_text(sheet.render(), encoding="utf-8")
        self._result.net_count += sheet.net_count
        logger.info("Wrote EPS schematic: %s (%d nets)", path, sheet.net_count)
        return path

    # ------------------------------------------------------------------
    # OBC schematic
    # ------------------------------------------------------------------

    def _generate_obc_schematic(
        self, output_dir: Path, active_ids: set[str]
    ) -> Path | None:
        """Generate the OBC + data-bus schematic."""
        sheet = _SchematicSheet(
            title=f"{self._design.mission_name} — OBC & Data Buses"
        )

        obc_ids = _OBC_COMPONENTS & active_ids
        if "obc_main" not in active_ids:
            logger.info("No OBC selected; skipping OBC schematic")
            return None

        # Row 0: OBC in the center
        center_x = _ORIGIN_X + _GRID_X
        placed_obc = self._place_component("obc_main", sheet, center_x, _ORIGIN_Y)

        # Row 1: I2C peripherals
        i2c_peripherals = [
            cid for cid in ("adcs_unit", "gps_rx", "prop_unit")
            if cid in active_ids
        ]
        col = 0
        for comp_id in i2c_peripherals:
            self._place_component(
                comp_id,
                sheet,
                _ORIGIN_X + col * _GRID_X,
                _ORIGIN_Y + _GRID_Y,
            )
            col += 1

        # Row 2: SPI peripherals and other loads
        spi_peripherals = [
            cid for cid in ("payload_main", "therm_heater")
            if cid in active_ids
        ]
        col = 0
        for comp_id in spi_peripherals:
            self._place_component(
                comp_id,
                sheet,
                _ORIGIN_X + col * _GRID_X,
                _ORIGIN_Y + 2 * _GRID_Y,
            )
            col += 1

        # Connections
        self._add_bus_connections(sheet, active_ids, target_comp_ids=obc_ids)

        path = output_dir / "cubesat_obc.kicad_sch"
        path.write_text(sheet.render(), encoding="utf-8")
        self._result.net_count += sheet.net_count
        logger.info("Wrote OBC schematic: %s (%d nets)", path, sheet.net_count)
        return path

    # ------------------------------------------------------------------
    # COM schematic
    # ------------------------------------------------------------------

    def _generate_com_schematic(
        self, output_dir: Path, active_ids: set[str]
    ) -> Path | None:
        """Generate the communication-subsystem schematic."""
        sheet = _SchematicSheet(
            title=f"{self._design.mission_name} — Communication"
        )

        com_ids = _COM_COMPONENTS & active_ids
        if not com_ids:
            logger.info("No COM components selected; skipping COM schematic")
            return None

        # Row 0: UHF chain — transceiver -> antenna
        col = 0
        for comp_id in ("com_uhf_trx", "com_uhf_ant"):
            if comp_id in active_ids:
                self._place_component(
                    comp_id,
                    sheet,
                    _ORIGIN_X + col * _GRID_X,
                    _ORIGIN_Y,
                )
                col += 1

        # Row 1: S-Band chain
        col = 0
        for comp_id in ("com_sband_tx", "com_sband_ant"):
            if comp_id in active_ids:
                self._place_component(
                    comp_id,
                    sheet,
                    _ORIGIN_X + col * _GRID_X,
                    _ORIGIN_Y + _GRID_Y,
                )
                col += 1

        self._add_bus_connections(sheet, active_ids, target_comp_ids=com_ids)

        path = output_dir / "cubesat_com.kicad_sch"
        path.write_text(sheet.render(), encoding="utf-8")
        self._result.net_count += sheet.net_count
        logger.info("Wrote COM schematic: %s (%d nets)", path, sheet.net_count)
        return path

    # ------------------------------------------------------------------
    # BOM generation
    # ------------------------------------------------------------------

    def _generate_bom(self, output_dir: Path, active_ids: set[str]) -> Path:
        """Generate a Bill of Materials CSV file."""
        path = output_dir / "bom.csv"

        components = self._design.get_all_components()
        rows: list[dict[str, Any]] = []

        for comp in components:
            comp_id = comp["id"]
            estimates = _BOM_ESTIMATES.get(comp_id, {})

            # Look up the reference designator we assigned
            placed = self._all_placed.get(comp_id)
            ref = placed.reference if placed else comp_id.upper()

            rows.append({
                "Reference": ref,
                "Value": comp["name"],
                "Component ID": comp_id,
                "Subsystem": comp.get("subsystem", ""),
                "Package": estimates.get("package", "N/A"),
                "Supplier": estimates.get("supplier", "N/A"),
                "Quantity": 1,
                "Unit Price (USD)": estimates.get("unit_price", 0.0),
                "Mass (g)": comp["mass_g"],
                "Power (W)": comp["power_w"],
            })

        fieldnames = [
            "Reference",
            "Value",
            "Component ID",
            "Subsystem",
            "Package",
            "Supplier",
            "Quantity",
            "Unit Price (USD)",
            "Mass (g)",
            "Power (W)",
        ]

        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        logger.info("Wrote BOM: %s (%d line items)", path, len(rows))
        return path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _place_component(
        self,
        comp_id: str,
        sheet: _SchematicSheet,
        x: float,
        y: float,
    ) -> _PlacedComponent | None:
        """Create a placed component from the catalog and add it to *sheet*.

        Returns:
            The placed component, or ``None`` if *comp_id* is not in the
            catalog or PIN_TEMPLATES.
        """
        # Find catalog entry
        catalog_comp = self._find_catalog_component(comp_id)
        if catalog_comp is None:
            logger.warning("Component %s not found in catalog; skipping", comp_id)
            return None

        # Build pin list from PIN_TEMPLATES
        pin_templates = PIN_TEMPLATES.get(comp_id, [])
        if not pin_templates:
            # Structure and other pinless components are placed but with no pins
            pass

        pins: list[dict[str, Any]] = []
        for i, pt in enumerate(pin_templates, start=1):
            pins.append({
                "name": pt["name"],
                "direction": pt["direction"],
                "voltage": pt["voltage"],
                "current_max": pt["current_max"],
                "number": str(i),
            })

        # Determine reference prefix
        prefix = self._ref_prefix(comp_id)
        reference = self._ref_alloc.allocate(prefix)

        # Build lib_id from subsystem and component name
        subsystem_name = catalog_comp.get("subsystem", "Module")
        lib_id = f"{subsystem_name}:{catalog_comp['name'].replace(' ', '_')}"

        estimates = _BOM_ESTIMATES.get(comp_id, {})

        placed = _PlacedComponent(
            comp_id=comp_id,
            name=catalog_comp["name"],
            reference=reference,
            lib_id=lib_id,
            x=x,
            y=y,
            pins=pins,
            properties={
                "package": estimates.get("package", ""),
                "voltage": catalog_comp.get("voltage", 0),
                "power_w": catalog_comp.get("power_w", 0),
            },
        )

        sheet.add_component(placed)
        self._all_placed[comp_id] = placed
        return placed

    def _add_bus_connections(
        self,
        sheet: _SchematicSheet,
        active_ids: set[str],
        target_comp_ids: set[str],
    ) -> None:
        """Add wires and net labels for bus connections relevant to *target_comp_ids*.

        Iterates over all BUS_RULES; for each connection where at least one
        endpoint is in *target_comp_ids* and both endpoints are in *active_ids*,
        adds a wire stub and net label.
        """
        for rule in BUS_RULES:
            net_name = rule.name

            for conn in rule.connections:
                src_id = conn.source_comp
                dst_id = conn.dest_comp

                # Both must be active
                if src_id not in active_ids or dst_id not in active_ids:
                    continue

                # At least one must be on this sheet
                if src_id not in target_comp_ids and dst_id not in target_comp_ids:
                    continue

                sheet.add_net(net_name)

                # Add wire stubs and labels for source pin
                src_placed = self._all_placed.get(src_id)
                if src_placed is not None and src_id in target_comp_ids:
                    pin_pos = self._get_pin_position(src_placed, conn.source_pin)
                    if pin_pos is not None:
                        px, py = pin_pos
                        wx = px + _WIRE_EXTENSION
                        sheet.add_wire(px, py, wx, py)
                        label_name = f"{net_name}_{conn.source_pin}"
                        sheet.add_label(label_name, wx, py)

                # Add wire stubs and labels for destination pin
                dst_placed = self._all_placed.get(dst_id)
                if dst_placed is not None and dst_id in target_comp_ids:
                    pin_pos = self._get_pin_position(dst_placed, conn.dest_pin)
                    if pin_pos is not None:
                        px, py = pin_pos
                        wx = px - _WIRE_EXTENSION
                        sheet.add_wire(wx, py, px, py)
                        label_name = f"{net_name}_{conn.dest_pin}"
                        sheet.add_label(label_name, wx, py)

    def _get_pin_position(
        self, comp: _PlacedComponent, pin_name: str
    ) -> tuple[float, float] | None:
        """Calculate the absolute position of a pin on a placed component.

        Returns:
            (x, y) tuple, or ``None`` if the pin is not found.
        """
        pin_count = len(comp.pins)
        body_h = max(pin_count * _PIN_LENGTH, 10.0)
        half_h = body_h / 2.0
        body_w = 15.0
        half_w = body_w / 2.0

        # Separate pins into left (input/power/bidir) and right (output)
        left_pins: list[dict[str, Any]] = []
        right_pins: list[dict[str, Any]] = []
        for p in comp.pins:
            if p.get("direction", "") == "OUTPUT":
                right_pins.append(p)
            else:
                left_pins.append(p)

        pin_y_start = half_h - _PIN_LENGTH

        # Check left pins
        for i, p in enumerate(left_pins):
            if p["name"] == pin_name:
                local_x = -(half_w + _PIN_LENGTH)
                local_y = pin_y_start - i * _PIN_LENGTH * 1.5
                return (comp.x + local_x, comp.y + local_y)

        # Check right pins
        for i, p in enumerate(right_pins):
            if p["name"] == pin_name:
                local_x = half_w + _PIN_LENGTH
                local_y = pin_y_start - i * _PIN_LENGTH * 1.5
                return (comp.x + local_x, comp.y + local_y)

        return None

    def _find_catalog_component(self, comp_id: str) -> dict[str, Any] | None:
        """Look up a component by ID across the COMPONENT_CATALOG and design extras."""
        # Search COMPONENT_CATALOG
        for subsystem_data in COMPONENT_CATALOG.values():
            for comp in subsystem_data["components"]:
                if comp["id"] == comp_id:
                    return {**comp, "subsystem": subsystem_data["name"]}

        # Check design-generated components (payload, structure)
        for comp in self._design.get_all_components():
            if comp["id"] == comp_id:
                return comp

        return None

    @staticmethod
    def _ref_prefix(comp_id: str) -> str:
        """Determine the KiCad reference prefix for a component ID."""
        if comp_id.startswith("eps_solar"):
            return "J"  # Solar panel connector
        if comp_id.startswith("eps_batt"):
            return "BT"
        if comp_id.startswith("com_") and "ant" in comp_id:
            return "ANT"
        if comp_id.startswith("structure"):
            return "MK"  # Mechanical
        # Default: IC / Module
        return "U"
