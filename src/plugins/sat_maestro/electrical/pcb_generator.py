"""KiCad PCB layout generator for CubeSat auto-design pipeline.

Generates valid KiCad 10 PCB files (.kicad_pcb, format version 20240108)
from a :class:`CubeSatDesign`.  The output is directly openable in KiCad
pcbnew and includes:

- PC/104-compliant board outline with mounting holes
- Component footprints placed on a 2.54 mm grid
- Copper zones (GND pour on B.Cu)
- Routed traces with width rules (power / signal / RF)
- Silkscreen annotations (references, board title, pin-1 markers)

All footprint definitions are inlined so the file is self-contained and
does not depend on any external KiCad library.
"""
from __future__ import annotations

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

_KICAD_PCB_VERSION = 20240108
_GENERATOR = "sat-maestro"
_GENERATOR_VERSION = "10.0.0"

_GRID = 2.54  # mm — standard 0.1" grid

# Board dimensions per CubeSat form factor (mm)
_BOARD_SIZES: dict[str, tuple[float, float]] = {
    "1U": (90.0, 95.0),
    "2U": (90.0, 95.0),
    "3U": (90.0, 95.0),
    "6U": (160.0, 95.0),
    "12U": (160.0, 95.0),
}

# Mounting hole: M3, 3.2 mm drill, 6.0 mm pad, 5 mm inset from edges
_MOUNT_HOLE_DRILL = 3.2
_MOUNT_HOLE_PAD = 6.0
_MOUNT_HOLE_INSET = 5.0

# Trace width rules (mm)
_TRACE_WIDTH: dict[str, float] = {
    "VBATT": 1.0,
    "5V": 0.8,
    "3V3": 0.5,
    "GND": 0.5,
    "SIGNAL": 0.25,
    "RF": 0.45,  # ~50 ohm on 1.6 mm FR4, er=4.5
}

# Zone clearance and minimum width (mm)
_ZONE_CLEARANCE = 0.3
_ZONE_MIN_WIDTH = 0.25

# Footprint library names for known component types
_FOOTPRINT_MAP: dict[str, str] = {
    "eps_pcu": "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
    "eps_batt": "Connector_PinHeader_1x02_P2.54mm_Vertical",
    "eps_solar": "Connector_PinHeader_1x02_P2.54mm_Vertical",
    "obc_main": "Package_QFP:LQFP-64_10x10mm_P0.5mm",
    "com_uhf_trx": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "com_uhf_ant": "Connector_Coaxial:SMA_Amphenol_132134_EdgeMount",
    "com_sband_tx": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "com_sband_ant": "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1",
    "adcs_unit": "Package_QFP:LQFP-48_7x7mm_P0.5mm",
    "gps_rx": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "prop_unit": "Connector_PinHeader_2x05_P2.54mm_Vertical",
    "therm_heater": "Connector_PinHeader_1x02_P2.54mm_Vertical",
    "payload_main": "Connector_PinHeader_2x20_P2.54mm_Vertical",
}

# Reference designator prefixes (mirrors schematic_generator)
_REF_PREFIX: dict[str, str] = {
    "eps_solar": "J",
    "eps_batt": "BT",
    "com_uhf_ant": "ANT",
    "com_sband_ant": "ANT",
    "structure_frame": "MK",
}

# Pad geometry per footprint type (simplified inline definitions)
# Each entry: list of (pad_number, pad_type, shape, rel_x, rel_y, size_x, size_y, drill)
# pad_type: "smd" | "thru_hole"  shape: "rect" | "roundrect" | "oval" | "circle"
_PAD_TEMPLATES: dict[str, list[tuple[str, str, str, float, float, float, float, float]]] = {
    "SOIC-8": [
        ("1", "smd", "rect",   -1.905, -2.6, 0.6, 1.5, 0.0),
        ("2", "smd", "rect",   -0.635, -2.6, 0.6, 1.5, 0.0),
        ("3", "smd", "rect",    0.635, -2.6, 0.6, 1.5, 0.0),
        ("4", "smd", "rect",    1.905, -2.6, 0.6, 1.5, 0.0),
        ("5", "smd", "rect",    1.905,  2.6, 0.6, 1.5, 0.0),
        ("6", "smd", "rect",    0.635,  2.6, 0.6, 1.5, 0.0),
        ("7", "smd", "rect",   -0.635,  2.6, 0.6, 1.5, 0.0),
        ("8", "smd", "rect",   -1.905,  2.6, 0.6, 1.5, 0.0),
    ],
    "SOIC-16": [
        *[
            (str(i + 1), "smd", "rect",
             -4.445 + i * 1.27, -3.4, 0.6, 1.5, 0.0)
            for i in range(8)
        ],
        *[
            (str(16 - i), "smd", "rect",
             -4.445 + i * 1.27, 3.4, 0.6, 1.5, 0.0)
            for i in range(8)
        ],
    ],
    "LQFP-64": [
        *[
            (str(i + 1), "smd", "rect",
             -5.5, -3.75 + i * 0.5, 1.5, 0.3, 0.0)
            for i in range(16)
        ],
        *[
            (str(i + 17), "smd", "rect",
             -3.75 + i * 0.5, 5.5, 0.3, 1.5, 0.0)
            for i in range(16)
        ],
        *[
            (str(i + 33), "smd", "rect",
             5.5, 3.75 - i * 0.5, 1.5, 0.3, 0.0)
            for i in range(16)
        ],
        *[
            (str(i + 49), "smd", "rect",
             3.75 - i * 0.5, -5.5, 0.3, 1.5, 0.0)
            for i in range(16)
        ],
    ],
    "LQFP-48": [
        *[
            (str(i + 1), "smd", "rect",
             -4.25, -2.75 + i * 0.5, 1.5, 0.3, 0.0)
            for i in range(12)
        ],
        *[
            (str(i + 13), "smd", "rect",
             -2.75 + i * 0.5, 4.25, 0.3, 1.5, 0.0)
            for i in range(12)
        ],
        *[
            (str(i + 25), "smd", "rect",
             4.25, 2.75 - i * 0.5, 1.5, 0.3, 0.0)
            for i in range(12)
        ],
        *[
            (str(i + 37), "smd", "rect",
             2.75 - i * 0.5, -4.25, 0.3, 1.5, 0.0)
            for i in range(12)
        ],
    ],
    "PINHEADER-1x2": [
        ("1", "thru_hole", "rect",  0.0, 0.0,    1.7, 1.7, 1.0),
        ("2", "thru_hole", "oval",  0.0, 2.54,   1.7, 1.7, 1.0),
    ],
    "PINHEADER-2x5": [
        *[
            (str(i * 2 + 1), "thru_hole",
             "rect" if i == 0 else "oval",
             -1.27, i * 2.54, 1.7, 1.7, 1.0)
            for i in range(5)
        ],
        *[
            (str(i * 2 + 2), "thru_hole", "oval",
             1.27, i * 2.54, 1.7, 1.7, 1.0)
            for i in range(5)
        ],
    ],
    "PINHEADER-2x20": [
        *[
            (str(i * 2 + 1), "thru_hole",
             "rect" if i == 0 else "oval",
             -1.27, i * 2.54, 1.7, 1.7, 1.0)
            for i in range(20)
        ],
        *[
            (str(i * 2 + 2), "thru_hole", "oval",
             1.27, i * 2.54, 1.7, 1.7, 1.0)
            for i in range(20)
        ],
    ],
    "SMA_EDGE": [
        ("1", "smd", "rect", 0.0, 0.0, 1.5, 1.5, 0.0),
        ("2", "smd", "rect", -2.54, 0.0, 1.5, 1.5, 0.0),
        ("3", "smd", "rect",  2.54, 0.0, 1.5, 1.5, 0.0),
    ],
    "UFL_SMT": [
        ("1", "smd", "rect", 0.0, 0.0, 1.0, 1.0, 0.0),
        ("2", "smd", "rect", -1.5, 0.0, 0.8, 0.8, 0.0),
        ("3", "smd", "rect",  1.5, 0.0, 0.8, 0.8, 0.0),
    ],
    "MOUNT_HOLE": [
        ("1", "thru_hole", "circle", 0.0, 0.0, _MOUNT_HOLE_PAD, _MOUNT_HOLE_PAD,
         _MOUNT_HOLE_DRILL),
    ],
}

# Map component IDs to pad template keys
_COMP_PAD_KEY: dict[str, str] = {
    "eps_pcu": "SOIC-16",
    "eps_batt": "PINHEADER-1x2",
    "eps_solar": "PINHEADER-1x2",
    "obc_main": "LQFP-64",
    "com_uhf_trx": "SOIC-8",
    "com_uhf_ant": "SMA_EDGE",
    "com_sband_tx": "SOIC-8",
    "com_sband_ant": "UFL_SMT",
    "adcs_unit": "LQFP-48",
    "gps_rx": "SOIC-8",
    "prop_unit": "PINHEADER-2x5",
    "therm_heater": "PINHEADER-1x2",
    "payload_main": "PINHEADER-2x20",
}

# Placement zones relative to board center (region, priority order)
_PLACEMENT_ZONES: dict[str, str] = {
    "eps_pcu": "center",
    "obc_main": "center",
    "adcs_unit": "center",
    "eps_batt": "edge_left",
    "eps_solar": "edge_left",
    "com_uhf_trx": "edge_right",
    "com_uhf_ant": "edge_top",
    "com_sband_tx": "edge_right",
    "com_sband_ant": "edge_top",
    "gps_rx": "center",
    "prop_unit": "edge_bottom",
    "therm_heater": "edge_bottom",
    "payload_main": "edge_right",
}

# Net classification for trace width selection
_NET_WIDTH_CLASS: dict[str, str] = {
    "BATT_BUS": "VBATT",
    "SOLAR_BUS": "VBATT",
    "5V_BUS": "5V",
    "3V3_BUS": "3V3",
    "GND_BUS": "GND",
    "I2C_BUS": "SIGNAL",
    "UART_UHF": "SIGNAL",
    "SPI_PAYLOAD": "SIGNAL",
    "RF_UHF": "RF",
    "RF_SBAND": "RF",
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PcbResult:
    """Result of PCB layout generation."""

    pcb_file: str = ""
    component_count: int = 0
    trace_count: int = 0
    net_count: int = 0
    board_size_mm: tuple[float, float] = (0.0, 0.0)

    def summary(self) -> str:
        """Return a human-readable summary."""
        return (
            f"PCB generated: {self.pcb_file}\n"
            f"  Board: {self.board_size_mm[0]:.1f} x {self.board_size_mm[1]:.1f} mm\n"
            f"  Components: {self.component_count}\n"
            f"  Nets: {self.net_count}\n"
            f"  Traces: {self.trace_count}"
        )


# ---------------------------------------------------------------------------
# Internal placement dataclasses
# ---------------------------------------------------------------------------

@dataclass
class _PlacedFootprint:
    """A footprint placed on the PCB."""

    comp_id: str
    reference: str
    value: str
    footprint_lib: str
    pad_key: str
    x: float
    y: float
    layer: str = "F.Cu"
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    pin_net_map: dict[str, tuple[int, str]] = field(default_factory=dict)
    # pin_net_map: pad_number -> (net_code, net_name)


@dataclass
class _NetDef:
    """A named net in the PCB."""

    code: int
    name: str


@dataclass
class _Segment:
    """A copper trace segment."""

    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    layer: str
    net_code: int
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class _DecouplingCap:
    """A decoupling capacitor placed near an IC."""

    reference: str
    x: float
    y: float
    vcc_net: tuple[int, str]
    gnd_net: tuple[int, str]
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Reference designator allocator
# ---------------------------------------------------------------------------

class _RefAllocator:
    """Allocate unique reference designators."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def allocate(self, prefix: str) -> str:
        count = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = count
        return f"{prefix}{count}"


# ---------------------------------------------------------------------------
# PCB S-expression builder helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _snap(value: float) -> float:
    """Snap a coordinate to the nearest grid point."""
    return round(round(value / _GRID) * _GRID, 4)


def _sexpr_pad(
    number: str,
    pad_type: str,
    shape: str,
    at_x: float,
    at_y: float,
    size_x: float,
    size_y: float,
    drill: float,
    layers: str,
    net_code: int = 0,
    net_name: str = "",
) -> str:
    """Build a KiCad pad S-expression."""
    parts: list[str] = []
    parts.append(f'      (pad "{number}" {pad_type} {shape}')
    parts.append(f"        (at {at_x:.4f} {at_y:.4f})")
    parts.append(f"        (size {size_x:.4f} {size_y:.4f})")
    if drill > 0:
        parts.append(f"        (drill {drill:.4f})")
    parts.append(f"        (layers {layers})")
    if net_code > 0:
        parts.append(f'        (net {net_code} "{net_name}")')
    parts.append(f'        (uuid "{_uid()}")')
    parts.append("      )")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

class PcbGenerator:
    """Generate a KiCad PCB layout from a CubeSat design.

    Produces a single ``.kicad_pcb`` file containing the board outline,
    footprints, traces, copper zones, and silkscreen annotations.

    Args:
        design: The CubeSat design from the wizard.
    """

    def __init__(self, design: CubeSatDesign) -> None:
        self._design = design
        self._ref_alloc = _RefAllocator()
        self._footprints: list[_PlacedFootprint] = []
        self._decoupling_caps: list[_DecouplingCap] = []
        self._nets: dict[str, _NetDef] = {}
        self._segments: list[_Segment] = []
        self._net_counter = 0
        self._board_w: float = 0.0
        self._board_h: float = 0.0
        self._origin_x: float = 0.0
        self._origin_y: float = 0.0

    # -- Public API --------------------------------------------------------

    def generate(self, output_dir: Path) -> PcbResult:
        """Generate the PCB layout and write to *output_dir*.

        Args:
            output_dir: Target directory (created if absent).

        Returns:
            A :class:`PcbResult` describing the generated file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        board_size = _BOARD_SIZES.get(self._design.sat_size, (90.0, 95.0))
        self._board_w, self._board_h = board_size

        # PCB origin at KiCad's typical sheet offset (so the board is
        # comfortably inside the drawing area)
        self._origin_x = 100.0
        self._origin_y = 100.0

        # Register mandatory nets
        self._register_net("")   # net 0 is always unconnected
        self._register_net("GND")
        self._register_net("3V3")
        self._register_net("5V")
        self._register_net("VBATT")
        self._register_net("VSOLAR")

        # Phase 1 — discover active components and register bus nets
        active_ids = {c["id"] for c in self._design.get_all_components()}
        self._register_bus_nets(active_ids)

        # Phase 2 — place footprints
        self._place_all_footprints(active_ids)

        # Phase 3 — assign nets to pads
        self._assign_pad_nets(active_ids)

        # Phase 4 — create traces
        self._route_traces(active_ids)

        # Phase 5 — render and write
        pcb_content = self._render_pcb()
        pcb_path = output_dir / f"{self._design.mission_name}_pcb.kicad_pcb"
        pcb_path.write_text(pcb_content, encoding="utf-8")

        total_components = len(self._footprints) + len(self._decoupling_caps)

        result = PcbResult(
            pcb_file=str(pcb_path),
            component_count=total_components,
            trace_count=len(self._segments),
            net_count=len(self._nets) - 1,  # exclude net 0
            board_size_mm=board_size,
        )

        logger.info(
            "PCB generation complete: %s (%d components, %d traces, %d nets)",
            pcb_path.name,
            result.component_count,
            result.trace_count,
            result.net_count,
        )
        return result

    # -- Net management ----------------------------------------------------

    def _register_net(self, name: str) -> _NetDef:
        """Register a net name and return its definition."""
        if name in self._nets:
            return self._nets[name]
        code = self._net_counter
        self._net_counter += 1
        net = _NetDef(code=code, name=name)
        self._nets[name] = net
        return net

    def _register_bus_nets(self, active_ids: set[str]) -> None:
        """Register nets from BUS_RULES that are active in this design."""
        for rule in BUS_RULES:
            has_active = any(
                conn.source_comp in active_ids and conn.dest_comp in active_ids
                for conn in rule.connections
            )
            if has_active:
                self._register_net(rule.name)
                # Also register per-pin sub-nets for more meaningful naming
                for conn in rule.connections:
                    if conn.source_comp in active_ids and conn.dest_comp in active_ids:
                        self._register_net(
                            f"{rule.name}_{conn.source_pin}"
                        )

    def _get_net(self, name: str) -> _NetDef:
        """Look up a net by name, returning unconnected net 0 if not found."""
        return self._nets.get(name, self._nets[""])

    # -- Footprint placement -----------------------------------------------

    def _place_all_footprints(self, active_ids: set[str]) -> None:
        """Place component footprints on the board using zone-based layout."""
        # Build placement coordinate buckets
        cx = self._origin_x + self._board_w / 2.0
        cy = self._origin_y + self._board_h / 2.0

        # Center zone: grid around board center
        center_slots = self._generate_grid_slots(
            cx - 15.0, cy - 15.0, cols=4, rows=4, spacing=_GRID * 4
        )
        # Edge zones
        edge_left_slots = self._generate_grid_slots(
            self._origin_x + 8.0, cy - 10.0, cols=1, rows=4, spacing=_GRID * 5
        )
        edge_right_slots = self._generate_grid_slots(
            self._origin_x + self._board_w - 18.0, cy - 10.0,
            cols=1, rows=4, spacing=_GRID * 5,
        )
        edge_top_slots = self._generate_grid_slots(
            cx - 10.0, self._origin_y + 8.0, cols=4, rows=1, spacing=_GRID * 5
        )
        edge_bottom_slots = self._generate_grid_slots(
            cx - 10.0, self._origin_y + self._board_h - 15.0,
            cols=4, rows=1, spacing=_GRID * 5,
        )

        zone_slots: dict[str, list[tuple[float, float]]] = {
            "center": center_slots,
            "edge_left": edge_left_slots,
            "edge_right": edge_right_slots,
            "edge_top": edge_top_slots,
            "edge_bottom": edge_bottom_slots,
        }
        zone_indices: dict[str, int] = {z: 0 for z in zone_slots}

        # Sort active component IDs by placement priority (ICs first)
        placement_order = sorted(
            (cid for cid in active_ids if cid != "structure_frame"),
            key=lambda cid: (
                0 if cid in ("eps_pcu", "obc_main") else
                1 if cid in ("adcs_unit", "gps_rx") else
                2
            ),
        )

        for comp_id in placement_order:
            zone_name = _PLACEMENT_ZONES.get(comp_id, "center")
            slots = zone_slots.get(zone_name, center_slots)
            idx = zone_indices.get(zone_name, 0)

            if idx >= len(slots):
                # Overflow to center
                slots = center_slots
                idx = zone_indices.get("center", 0)
                zone_name = "center"

            x, y = slots[idx]
            zone_indices[zone_name] = idx + 1

            fp = self._create_footprint(comp_id, x, y)
            if fp is not None:
                self._footprints.append(fp)

                # Add decoupling cap for ICs
                if comp_id in ("eps_pcu", "obc_main", "adcs_unit",
                               "com_uhf_trx", "com_sband_tx", "gps_rx"):
                    self._add_decoupling_cap(comp_id, x, y)

    @staticmethod
    def _generate_grid_slots(
        start_x: float,
        start_y: float,
        cols: int,
        rows: int,
        spacing: float,
    ) -> list[tuple[float, float]]:
        """Generate snapped grid positions."""
        slots: list[tuple[float, float]] = []
        for r in range(rows):
            for c in range(cols):
                slots.append((
                    _snap(start_x + c * spacing),
                    _snap(start_y + r * spacing),
                ))
        return slots

    def _create_footprint(
        self, comp_id: str, x: float, y: float
    ) -> _PlacedFootprint | None:
        """Create a placed footprint record for a component."""
        catalog_comp = self._find_catalog_component(comp_id)
        if catalog_comp is None:
            logger.warning("Component %s not in catalog; skipping", comp_id)
            return None

        pad_key = _COMP_PAD_KEY.get(comp_id)
        if pad_key is None:
            logger.warning("No pad template for %s; skipping", comp_id)
            return None

        prefix = _REF_PREFIX.get(comp_id, "U")
        reference = self._ref_alloc.allocate(prefix)
        footprint_lib = _FOOTPRINT_MAP.get(comp_id, f"SatMaestro:{comp_id}")

        return _PlacedFootprint(
            comp_id=comp_id,
            reference=reference,
            value=catalog_comp["name"],
            footprint_lib=footprint_lib,
            pad_key=pad_key,
            x=_snap(x),
            y=_snap(y),
        )

    def _add_decoupling_cap(
        self, near_comp_id: str, comp_x: float, comp_y: float
    ) -> None:
        """Place a 100 nF decoupling capacitor near an IC."""
        cap_ref = self._ref_alloc.allocate("C")

        # Determine which power net this IC uses
        pin_templates = PIN_TEMPLATES.get(near_comp_id, [])
        vcc_pin = next(
            (p for p in pin_templates
             if p["name"] in ("VCC", "VIN", "3V3_OUT", "5V_OUT")
             and p["direction"] in ("INPUT", "OUTPUT")),
            None,
        )

        if vcc_pin is not None:
            voltage = vcc_pin["voltage"]
            if voltage <= 3.5:
                net_name = "3V3"
            elif voltage <= 5.5:
                net_name = "5V"
            else:
                net_name = "VBATT"
        else:
            net_name = "3V3"

        vcc_net = self._get_net(net_name)
        gnd_net = self._get_net("GND")

        self._decoupling_caps.append(_DecouplingCap(
            reference=cap_ref,
            x=_snap(comp_x + _GRID * 3),
            y=_snap(comp_y + _GRID * 1),
            vcc_net=(vcc_net.code, vcc_net.name),
            gnd_net=(gnd_net.code, gnd_net.name),
        ))

    # -- Pad-to-net assignment ---------------------------------------------

    def _assign_pad_nets(self, active_ids: set[str]) -> None:
        """Assign net codes to footprint pads based on PIN_TEMPLATES and BUS_RULES."""
        for fp in self._footprints:
            comp_id = fp.comp_id
            pin_templates = PIN_TEMPLATES.get(comp_id, [])
            pad_templates = _PAD_TEMPLATES.get(fp.pad_key, [])

            for pin_idx, pin_tmpl in enumerate(pin_templates):
                pin_name = pin_tmpl["name"]
                # Find which bus net this pin belongs to
                net_name = self._resolve_pin_net(comp_id, pin_name, active_ids)

                # Map pin index to pad number (1-indexed, wrapping if needed)
                if pin_idx < len(pad_templates):
                    pad_num = pad_templates[pin_idx][0]
                else:
                    pad_num = str(pin_idx + 1)

                net_def = self._get_net(net_name)
                fp.pin_net_map[pad_num] = (net_def.code, net_def.name)

    def _resolve_pin_net(
        self, comp_id: str, pin_name: str, active_ids: set[str]
    ) -> str:
        """Determine the net name for a component pin from BUS_RULES."""
        # GND is always GND
        if pin_name == "GND":
            return "GND"

        # Search bus rules for a connection involving this component+pin
        for rule in BUS_RULES:
            for conn in rule.connections:
                if conn.source_comp not in active_ids or conn.dest_comp not in active_ids:
                    continue
                if conn.source_comp == comp_id and conn.source_pin == pin_name:
                    return rule.name
                if conn.dest_comp == comp_id and conn.dest_pin == pin_name:
                    return rule.name

        # Power pins not on any bus get a generic power net
        if pin_name in ("VCC", "VIN"):
            return "3V3"
        if pin_name in ("3V3_OUT",):
            return "3V3"
        if pin_name in ("5V_OUT",):
            return "5V"
        if pin_name == "BATT" or pin_name == "BATT_OUT":
            return "VBATT"
        if pin_name == "VOUT":
            return "VSOLAR"

        return ""

    # -- Trace routing -----------------------------------------------------

    def _route_traces(self, active_ids: set[str]) -> None:
        """Create trace segments for bus connections between placed footprints."""
        fp_lookup: dict[str, _PlacedFootprint] = {
            fp.comp_id: fp for fp in self._footprints
        }

        for rule in BUS_RULES:
            width_class = _NET_WIDTH_CLASS.get(rule.name, "SIGNAL")
            trace_w = _TRACE_WIDTH.get(width_class, 0.25)
            net_def = self._get_net(rule.name)

            if net_def.code == 0:
                continue

            for conn in rule.connections:
                if conn.source_comp not in active_ids or conn.dest_comp not in active_ids:
                    continue

                src_fp = fp_lookup.get(conn.source_comp)
                dst_fp = fp_lookup.get(conn.dest_comp)
                if src_fp is None or dst_fp is None:
                    continue

                # Route from source footprint center to destination footprint
                # center using L-shaped routing (horizontal then vertical)
                src_x, src_y = src_fp.x, src_fp.y
                dst_x, dst_y = dst_fp.x, dst_fp.y

                # Offset source and destination slightly based on pin position
                src_pin_offset = self._get_pin_pad_offset(
                    src_fp, conn.source_pin
                )
                dst_pin_offset = self._get_pin_pad_offset(
                    dst_fp, conn.dest_pin
                )

                sx = _snap(src_x + src_pin_offset[0])
                sy = _snap(src_y + src_pin_offset[1])
                dx = _snap(dst_x + dst_pin_offset[0])
                dy = _snap(dst_y + dst_pin_offset[1])

                # L-route: horizontal leg then vertical leg
                mid_x = _snap(dx)
                mid_y = _snap(sy)

                layer = "F.Cu"
                if width_class == "RF":
                    # RF traces stay on top layer with controlled impedance
                    layer = "F.Cu"

                # Horizontal segment
                if abs(sx - mid_x) > 0.01:
                    self._segments.append(_Segment(
                        x1=sx, y1=sy, x2=mid_x, y2=mid_y,
                        width=trace_w, layer=layer, net_code=net_def.code,
                    ))

                # Vertical segment
                if abs(mid_y - dy) > 0.01:
                    self._segments.append(_Segment(
                        x1=mid_x, y1=mid_y, x2=dx, y2=dy,
                        width=trace_w, layer=layer, net_code=net_def.code,
                    ))

        # Route decoupling cap traces (short stubs to nearby VCC and GND)
        for cap in self._decoupling_caps:
            # VCC pad (pad 1) stub
            self._segments.append(_Segment(
                x1=cap.x, y1=cap.y,
                x2=_snap(cap.x - _GRID * 2), y2=cap.y,
                width=0.5, layer="F.Cu", net_code=cap.vcc_net[0],
            ))
            # GND pad (pad 2) stub
            self._segments.append(_Segment(
                x1=cap.x, y1=_snap(cap.y + 1.27),
                x2=_snap(cap.x - _GRID * 2), y2=_snap(cap.y + 1.27),
                width=0.5, layer="F.Cu", net_code=cap.gnd_net[0],
            ))

    def _get_pin_pad_offset(
        self, fp: _PlacedFootprint, pin_name: str
    ) -> tuple[float, float]:
        """Get approximate pad offset from footprint origin for a pin name."""
        pin_templates = PIN_TEMPLATES.get(fp.comp_id, [])
        pad_templates = _PAD_TEMPLATES.get(fp.pad_key, [])

        for pin_idx, pin_tmpl in enumerate(pin_templates):
            if pin_tmpl["name"] == pin_name and pin_idx < len(pad_templates):
                pad = pad_templates[pin_idx]
                return (pad[3], pad[4])  # rel_x, rel_y

        return (0.0, 0.0)

    # -- KiCad PCB rendering -----------------------------------------------

    def _render_pcb(self) -> str:
        """Render the complete .kicad_pcb S-expression."""
        parts: list[str] = []

        parts.append(self._render_header())
        parts.append(self._render_general())
        parts.append(self._render_paper())
        parts.append(self._render_layers())
        parts.append(self._render_setup())
        parts.append(self._render_nets())
        parts.append(self._render_board_outline())
        parts.append(self._render_mounting_holes())
        parts.append(self._render_footprints())
        parts.append(self._render_decoupling_caps())
        parts.append(self._render_segments())
        parts.append(self._render_gnd_zone())
        parts.append(self._render_silkscreen_title())
        parts.append(")")
        parts.append("")

        return "\n".join(parts)

    def _render_header(self) -> str:
        return (
            f"(kicad_pcb (version {_KICAD_PCB_VERSION}) "
            f'(generator "{_GENERATOR}") '
            f'(generator_version "{_GENERATOR_VERSION}")'
        )

    def _render_general(self) -> str:
        return "  (general (thickness 1.6) (legacy_teardrops no))"

    def _render_paper(self) -> str:
        return '  (paper "A4")'

    def _render_layers(self) -> str:
        lines = [
            "  (layers",
            '    (0 "F.Cu" signal)',
            '    (1 "In1.Cu" signal)',
            '    (2 "In2.Cu" signal)',
            '    (31 "B.Cu" signal)',
            '    (32 "B.Adhes" user "B.Adhesive")',
            '    (33 "F.Adhes" user "F.Adhesive")',
            '    (34 "B.Paste" user)',
            '    (35 "F.Paste" user)',
            '    (36 "B.SilkS" user "B.Silkscreen")',
            '    (37 "F.SilkS" user "F.Silkscreen")',
            '    (38 "B.Mask" user)',
            '    (39 "F.Mask" user)',
            '    (40 "Dwgs.User" user "User.Drawings")',
            '    (41 "Cmts.User" user "User.Comments")',
            '    (42 "Eco1.User" user "User.Eco1")',
            '    (43 "Eco2.User" user "User.Eco2")',
            '    (44 "Edge.Cuts" user)',
            '    (45 "Margin" user)',
            '    (46 "B.CrtYd" user "B.Courtyard")',
            '    (47 "F.CrtYd" user "F.Courtyard")',
            '    (48 "B.Fab" user)',
            '    (49 "F.Fab" user)',
            "  )",
        ]
        return "\n".join(lines)

    def _render_setup(self) -> str:
        lines = [
            "  (setup",
            "    (pad_to_mask_clearance 0.05)",
            "    (allow_soldermask_bridges_in_footprints no)",
            "    (pcbplotparams",
            '      (layerselection 0x00010fc_ffffffff)',
            "      (plot_on_all_layers_selection 0x0000000_00000000)",
            '      (disableapertmacros no)',
            '      (usegerberextensions no)',
            '      (usegerberattributes yes)',
            '      (usegerberadvancedattributes yes)',
            '      (creategerberjobfile yes)',
            "      (dashed_line_dash_ratio 12.000000)",
            "      (dashed_line_gap_ratio 3.000000)",
            '      (svgprecision 4)',
            '      (plotframeref no)',
            '      (viasonmask no)',
            "      (mode 1)",
            "      (useauxorigin no)",
            "      (hpglpennumber 1)",
            "      (hpglpenspeed 20)",
            "      (hpglpendiameter 15.000000)",
            "      (pdf_front_fp_property_popups yes)",
            "      (pdf_back_fp_property_popups yes)",
            '      (dxfpolygonmode yes)',
            '      (dxfimperialunits yes)',
            '      (dxfusepcbnewfont yes)',
            '      (psnegative no)',
            '      (psa4output no)',
            "      (plotreference yes)",
            "      (plotvalue no)",
            "      (plotfptext yes)",
            "      (plotinvisibletext no)",
            "      (sketchpadsonfab no)",
            "      (subtractmaskfromsilk no)",
            "      (outputformat 1)",
            "      (mirror no)",
            "      (drillshape 1)",
            "      (scaleselection 1)",
            '      (outputdirectory "")',
            "    )",
            "  )",
        ]
        return "\n".join(lines)

    def _render_nets(self) -> str:
        lines: list[str] = []
        for net_def in sorted(self._nets.values(), key=lambda n: n.code):
            lines.append(f'  (net {net_def.code} "{net_def.name}")')
        return "\n".join(lines)

    def _render_board_outline(self) -> str:
        """Render Edge.Cuts rectangle for board outline."""
        ox = self._origin_x
        oy = self._origin_y
        w = self._board_w
        h = self._board_h

        # Corner radius for rounded rectangle (CubeSat PC/104 standard)
        lines = [
            f"",
            f"  ; Board outline — {self._design.sat_size} PC/104 ({w:.1f} x {h:.1f} mm)",
            f'  (gr_line (start {ox:.4f} {oy:.4f}) (end {ox + w:.4f} {oy:.4f}) '
            f'(stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "{_uid()}"))',
            f'  (gr_line (start {ox + w:.4f} {oy:.4f}) (end {ox + w:.4f} {oy + h:.4f}) '
            f'(stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "{_uid()}"))',
            f'  (gr_line (start {ox + w:.4f} {oy + h:.4f}) (end {ox:.4f} {oy + h:.4f}) '
            f'(stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "{_uid()}"))',
            f'  (gr_line (start {ox:.4f} {oy + h:.4f}) (end {ox:.4f} {oy:.4f}) '
            f'(stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "{_uid()}"))',
        ]
        return "\n".join(lines)

    def _render_mounting_holes(self) -> str:
        """Render 4 corner mounting holes (M3)."""
        ox = self._origin_x
        oy = self._origin_y
        w = self._board_w
        h = self._board_h
        inset = _MOUNT_HOLE_INSET

        holes = [
            (ox + inset, oy + inset),
            (ox + w - inset, oy + inset),
            (ox + inset, oy + h - inset),
            (ox + w - inset, oy + h - inset),
        ]

        gnd_net = self._get_net("GND")
        lines: list[str] = ["\n  ; Mounting holes (M3, 3.2mm drill)"]

        for i, (hx, hy) in enumerate(holes, start=1):
            hole_ref = self._ref_alloc.allocate("MH")
            hole_uuid = _uid()
            pad_uuid = _uid()

            lines.append(
                f'  (footprint "MountingHole:MountingHole_3.2mm_M3_Pad" '
                f'(layer "F.Cu") (uuid "{hole_uuid}")'
            )
            lines.append(f"    (at {hx:.4f} {hy:.4f})")
            lines.append(
                f'    (property "Reference" "{hole_ref}" '
                f'(at 0 -3.5 0) (layer "F.SilkS") (uuid "{_uid()}")'
            )
            lines.append(
                f'      (effects (font (size 1 1) (thickness 0.15)))'
            )
            lines.append("    )")
            lines.append(
                f'    (property "Value" "MountingHole_M3" '
                f'(at 0 3.5 0) (layer "F.Fab") (hide yes) (uuid "{_uid()}")'
            )
            lines.append(
                f'      (effects (font (size 1 1) (thickness 0.15)))'
            )
            lines.append("    )")
            lines.append(
                f'    (pad "1" thru_hole circle'
            )
            lines.append(
                f"      (at 0 0)"
            )
            lines.append(
                f"      (size {_MOUNT_HOLE_PAD:.4f} {_MOUNT_HOLE_PAD:.4f})"
            )
            lines.append(
                f"      (drill {_MOUNT_HOLE_DRILL:.4f})"
            )
            lines.append(
                f'      (layers "*.Cu" "*.Mask")'
            )
            lines.append(
                f'      (net {gnd_net.code} "{gnd_net.name}")'
            )
            lines.append(
                f'      (uuid "{pad_uuid}")'
            )
            lines.append("    )")
            lines.append("  )")

        return "\n".join(lines)

    def _render_footprints(self) -> str:
        """Render all placed component footprints."""
        parts: list[str] = ["\n  ; Component footprints"]

        for fp in self._footprints:
            parts.append(self._render_single_footprint(fp))

        return "\n".join(parts)

    def _render_single_footprint(self, fp: _PlacedFootprint) -> str:
        """Render one footprint S-expression."""
        pad_templates = _PAD_TEMPLATES.get(fp.pad_key, [])
        lines: list[str] = []

        lines.append(
            f'  (footprint "{fp.footprint_lib}" '
            f'(layer "{fp.layer}") (uuid "{fp.uuid}")'
        )
        lines.append(f"    (at {fp.x:.4f} {fp.y:.4f})")

        # Reference on silkscreen
        lines.append(
            f'    (property "Reference" "{fp.reference}" '
            f'(at 0 {-self._body_half_h(fp.pad_key) - 2.0:.4f} 0) '
            f'(layer "F.SilkS") (uuid "{_uid()}")'
        )
        lines.append(
            f'      (effects (font (size 1 1) (thickness 0.15)))'
        )
        lines.append("    )")

        # Value on fabrication layer (hidden)
        lines.append(
            f'    (property "Value" "{fp.value}" '
            f'(at 0 {self._body_half_h(fp.pad_key) + 2.0:.4f} 0) '
            f'(layer "F.Fab") (hide yes) (uuid "{_uid()}")'
        )
        lines.append(
            f'      (effects (font (size 1 1) (thickness 0.15)))'
        )
        lines.append("    )")

        # Footprint property
        lines.append(
            f'    (property "Footprint" "{fp.footprint_lib}" '
            f'(at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{_uid()}")'
        )
        lines.append(
            f'      (effects (font (size 1 1) (thickness 0.15)))'
        )
        lines.append("    )")

        # Courtyard rectangle
        half_h = self._body_half_h(fp.pad_key)
        half_w = self._body_half_w(fp.pad_key)
        crt_margin = 0.5

        lines.append(
            f'    (fp_rect (start {-half_w - crt_margin:.4f} {-half_h - crt_margin:.4f}) '
            f'(end {half_w + crt_margin:.4f} {half_h + crt_margin:.4f}) '
            f'(stroke (width 0.05) (type default)) (layer "F.CrtYd") (uuid "{_uid()}"))'
        )

        # Fabrication layer body outline
        lines.append(
            f'    (fp_rect (start {-half_w:.4f} {-half_h:.4f}) '
            f'(end {half_w:.4f} {half_h:.4f}) '
            f'(stroke (width 0.1) (type default)) (layer "F.Fab") (uuid "{_uid()}"))'
        )

        # Pin 1 marker on silkscreen (small circle at pad 1 location)
        if pad_templates:
            p1 = pad_templates[0]
            p1_x, p1_y = p1[3], p1[4]
            marker_offset = 0.8
            lines.append(
                f'    (fp_circle (center {p1_x - marker_offset:.4f} {p1_y - marker_offset:.4f}) '
                f'(end {p1_x - marker_offset + 0.3:.4f} {p1_y - marker_offset:.4f}) '
                f'(stroke (width 0.12) (type default)) (fill none) '
                f'(layer "F.SilkS") (uuid "{_uid()}"))'
            )

        # Pads
        for pad in pad_templates:
            pad_num, pad_type, shape, rel_x, rel_y, sz_x, sz_y, drill = pad
            net_code = 0
            net_name = ""

            if pad_num in fp.pin_net_map:
                net_code, net_name = fp.pin_net_map[pad_num]

            if pad_type == "thru_hole":
                layers = '"*.Cu" "*.Mask"'
            else:
                layers = '"F.Cu" "F.Paste" "F.Mask"'

            lines.append(_sexpr_pad(
                number=pad_num,
                pad_type=pad_type,
                shape=shape,
                at_x=rel_x,
                at_y=rel_y,
                size_x=sz_x,
                size_y=sz_y,
                drill=drill,
                layers=layers,
                net_code=net_code,
                net_name=net_name,
            ))

        lines.append("  )")
        return "\n".join(lines)

    def _render_decoupling_caps(self) -> str:
        """Render decoupling capacitor footprints (0402 / 0603 SMD)."""
        if not self._decoupling_caps:
            return ""

        gnd_net = self._get_net("GND")
        lines: list[str] = ["\n  ; Decoupling capacitors (100nF)"]

        for cap in self._decoupling_caps:
            lines.append(
                f'  (footprint "Capacitor_SMD:C_0603_1608Metric" '
                f'(layer "F.Cu") (uuid "{cap.uuid}")'
            )
            lines.append(f"    (at {cap.x:.4f} {cap.y:.4f})")

            # Reference
            lines.append(
                f'    (property "Reference" "{cap.reference}" '
                f'(at 0 -1.5 0) (layer "F.SilkS") (uuid "{_uid()}")'
            )
            lines.append(
                f'      (effects (font (size 0.8 0.8) (thickness 0.12)))'
            )
            lines.append("    )")

            # Value
            lines.append(
                f'    (property "Value" "100nF" '
                f'(at 0 1.5 0) (layer "F.Fab") (uuid "{_uid()}")'
            )
            lines.append(
                f'      (effects (font (size 0.8 0.8) (thickness 0.12)))'
            )
            lines.append("    )")

            # Courtyard
            lines.append(
                f'    (fp_rect (start -1.1 -0.6) (end 1.1 0.6) '
                f'(stroke (width 0.05) (type default)) (layer "F.CrtYd") (uuid "{_uid()}"))'
            )

            # Fab outline
            lines.append(
                f'    (fp_rect (start -0.8 -0.4) (end 0.8 0.4) '
                f'(stroke (width 0.1) (type default)) (layer "F.Fab") (uuid "{_uid()}"))'
            )

            # Pad 1: VCC side
            lines.append(_sexpr_pad(
                number="1", pad_type="smd", shape="roundrect",
                at_x=-0.75, at_y=0.0, size_x=0.8, size_y=0.95,
                drill=0.0, layers='"F.Cu" "F.Paste" "F.Mask"',
                net_code=cap.vcc_net[0], net_name=cap.vcc_net[1],
            ))

            # Pad 2: GND side
            lines.append(_sexpr_pad(
                number="2", pad_type="smd", shape="roundrect",
                at_x=0.75, at_y=0.0, size_x=0.8, size_y=0.95,
                drill=0.0, layers='"F.Cu" "F.Paste" "F.Mask"',
                net_code=gnd_net.code, net_name=gnd_net.name,
            ))

            lines.append("  )")

        return "\n".join(lines)

    def _render_segments(self) -> str:
        """Render all copper trace segments."""
        if not self._segments:
            return ""

        lines: list[str] = ["\n  ; Copper traces"]
        for seg in self._segments:
            lines.append(
                f"  (segment "
                f"(start {seg.x1:.4f} {seg.y1:.4f}) "
                f"(end {seg.x2:.4f} {seg.y2:.4f}) "
                f"(width {seg.width:.4f}) "
                f'(layer "{seg.layer}") '
                f"(net {seg.net_code}) "
                f'(uuid "{seg.uuid}"))'
            )
        return "\n".join(lines)

    def _render_gnd_zone(self) -> str:
        """Render GND copper pour zone on B.Cu."""
        gnd_net = self._get_net("GND")
        ox = self._origin_x
        oy = self._origin_y
        w = self._board_w
        h = self._board_h

        # Inset the zone slightly from board edge
        margin = 0.5

        lines = [
            f"\n  ; GND copper pour on B.Cu",
            f'  (zone (net {gnd_net.code}) (net_name "{gnd_net.name}") '
            f'(layer "B.Cu") (uuid "{_uid()}")',
            f"    (hatch edge 0.5)",
            f"    (connect_pads (clearance {_ZONE_CLEARANCE}))",
            f"    (min_thickness {_ZONE_MIN_WIDTH})",
            f"    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))",
            f"    (polygon",
            f"      (pts",
            f"        (xy {ox + margin:.4f} {oy + margin:.4f})",
            f"        (xy {ox + w - margin:.4f} {oy + margin:.4f})",
            f"        (xy {ox + w - margin:.4f} {oy + h - margin:.4f})",
            f"        (xy {ox + margin:.4f} {oy + h - margin:.4f})",
            f"      )",
            f"    )",
            f"  )",
        ]

        # Power plane section on In1.Cu for 3V3
        net_3v3 = self._get_net("3V3")
        # Cover left half of the board
        mid_x = ox + w / 2.0
        lines.extend([
            f"\n  ; 3V3 power plane section on In1.Cu",
            f'  (zone (net {net_3v3.code}) (net_name "{net_3v3.name}") '
            f'(layer "In1.Cu") (uuid "{_uid()}")',
            f"    (hatch edge 0.5)",
            f"    (connect_pads (clearance {_ZONE_CLEARANCE}))",
            f"    (min_thickness {_ZONE_MIN_WIDTH})",
            f"    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))",
            f"    (polygon",
            f"      (pts",
            f"        (xy {ox + margin:.4f} {oy + margin:.4f})",
            f"        (xy {mid_x:.4f} {oy + margin:.4f})",
            f"        (xy {mid_x:.4f} {oy + h - margin:.4f})",
            f"        (xy {ox + margin:.4f} {oy + h - margin:.4f})",
            f"      )",
            f"    )",
            f"  )",
        ])

        # Power plane section on In1.Cu for 5V (right half)
        net_5v = self._get_net("5V")
        lines.extend([
            f"\n  ; 5V power plane section on In1.Cu",
            f'  (zone (net {net_5v.code}) (net_name "{net_5v.name}") '
            f'(layer "In1.Cu") (uuid "{_uid()}")',
            f"    (hatch edge 0.5)",
            f"    (connect_pads (clearance {_ZONE_CLEARANCE}))",
            f"    (min_thickness {_ZONE_MIN_WIDTH})",
            f"    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))",
            f"    (polygon",
            f"      (pts",
            f"        (xy {mid_x:.4f} {oy + margin:.4f})",
            f"        (xy {ox + w - margin:.4f} {oy + margin:.4f})",
            f"        (xy {ox + w - margin:.4f} {oy + h - margin:.4f})",
            f"        (xy {mid_x:.4f} {oy + h - margin:.4f})",
            f"      )",
            f"    )",
            f"  )",
        ])

        return "\n".join(lines)

    def _render_silkscreen_title(self) -> str:
        """Render silkscreen text: board title, revision, and design info."""
        ox = self._origin_x
        oy = self._origin_y
        w = self._board_w
        h = self._board_h

        title = self._design.mission_name
        subtitle = f"{self._design.sat_size} CubeSat PCB"
        revision = "Rev A"

        # Place title in lower-left area of the board
        title_x = ox + 10.0
        title_y = oy + h - 8.0

        lines = [
            f"\n  ; Silkscreen annotations",
            f'  (gr_text "{title}" (at {title_x:.4f} {title_y:.4f} 0) '
            f'(layer "F.SilkS") (uuid "{_uid()}")',
            f"    (effects (font (size 2 2) (thickness 0.3)))",
            f"  )",
            f'  (gr_text "{subtitle}" (at {title_x:.4f} {title_y + 3.0:.4f} 0) '
            f'(layer "F.SilkS") (uuid "{_uid()}")',
            f"    (effects (font (size 1.5 1.5) (thickness 0.2)))",
            f"  )",
            f'  (gr_text "{revision}" (at {title_x:.4f} {title_y + 5.5:.4f} 0) '
            f'(layer "F.SilkS") (uuid "{_uid()}")',
            f"    (effects (font (size 1 1) (thickness 0.15)))",
            f"  )",
            f'  (gr_text "Generated by sat-maestro" '
            f'(at {ox + w - 35.0:.4f} {title_y + 5.5:.4f} 0) '
            f'(layer "F.SilkS") (uuid "{_uid()}")',
            f"    (effects (font (size 0.8 0.8) (thickness 0.12)))",
            f"  )",
        ]

        return "\n".join(lines)

    # -- Geometry helpers --------------------------------------------------

    @staticmethod
    def _body_half_h(pad_key: str) -> float:
        """Approximate half-height of a footprint body based on pad template."""
        pads = _PAD_TEMPLATES.get(pad_key, [])
        if not pads:
            return 2.0
        max_y = max(abs(p[4]) + p[6] / 2.0 for p in pads)
        return max_y + 0.5

    @staticmethod
    def _body_half_w(pad_key: str) -> float:
        """Approximate half-width of a footprint body based on pad template."""
        pads = _PAD_TEMPLATES.get(pad_key, [])
        if not pads:
            return 2.0
        max_x = max(abs(p[3]) + p[5] / 2.0 for p in pads)
        return max_x + 0.5

    # -- Catalog lookup ----------------------------------------------------

    def _find_catalog_component(self, comp_id: str) -> dict[str, Any] | None:
        """Look up a component by ID in the catalog or design extras."""
        for subsystem_data in COMPONENT_CATALOG.values():
            for comp in subsystem_data["components"]:
                if comp["id"] == comp_id:
                    return {**comp, "subsystem": subsystem_data["name"]}

        for comp in self._design.get_all_components():
            if comp["id"] == comp_id:
                return comp

        return None
