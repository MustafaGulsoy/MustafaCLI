"""FreeCAD CubeSat model builder via XML-RPC.

Creates detailed, realistic CubeSat 3D models in FreeCAD by sending
Python code through the FreeCAD MCP RPC server. Each subsystem component
is modelled with representative geometry rather than simple boxes.
"""
from __future__ import annotations

import logging
import math
import textwrap
import xmlrpc.client
from dataclasses import dataclass, field
from typing import Any

from ...cubesat_wizard import COMPONENT_CATALOG, CubeSatDesign

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dimension lookup (mm) for CubeSat form factors
# ---------------------------------------------------------------------------

CUBESAT_DIMS_MM: dict[str, tuple[float, float, float]] = {
    "1U": (100.0, 100.0, 113.5),
    "2U": (100.0, 100.0, 227.0),
    "3U": (100.0, 100.0, 340.5),
    "6U": (200.0, 100.0, 340.5),
    "12U": (200.0, 200.0, 340.5),
}

# Rail cross-section: L-profile leg length and thickness
RAIL_LEG: float = 5.0  # mm
RAIL_THICK: float = 1.5  # mm

# Plate dimensions
PLATE_THICK: float = 1.5  # mm
MOUNTING_HOLE_D: float = 3.2  # mm  (M3 clearance)
MOUNTING_HOLE_INSET: float = 6.0  # mm from plate edge

# PCB standard
PCB_WIDTH: float = 90.0  # mm
PCB_DEPTH: float = 90.0  # mm
PCB_THICK: float = 1.6  # mm
PCB_INSET: float = 5.0  # mm from frame inner wall

# Spacer between stacked boards
STACK_SPACER: float = 15.0  # mm total stack pitch per board

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class FreecadModelResult:
    """Summary returned after a FreeCAD model build.

    Attributes:
        document_name: Name of the FreeCAD document that was created.
        object_count: Total number of FreeCAD objects in the document.
        has_solar_panels: Whether deployable solar panels were created.
        has_antenna: Whether any antenna geometry was created.
    """

    document_name: str
    object_count: int
    has_solar_panels: bool
    has_antenna: bool


# ---------------------------------------------------------------------------
# Color palette (R, G, B) in 0-1 range
# ---------------------------------------------------------------------------

_COLORS: dict[str, tuple[float, float, float]] = {
    "frame_gray": (0.65, 0.65, 0.68),
    "plate_gray": (0.72, 0.72, 0.75),
    "pcb_green": (0.0, 0.45, 0.15),
    "pcb_dark_green": (0.0, 0.35, 0.10),
    "ic_black": (0.12, 0.12, 0.14),
    "pin_gold": (0.83, 0.69, 0.22),
    "battery_amber": (0.85, 0.65, 0.0),
    "battery_holder": (0.25, 0.25, 0.28),
    "solar_blue": (0.05, 0.05, 0.35),
    "solar_cell_line": (0.10, 0.10, 0.50),
    "hinge_silver": (0.78, 0.78, 0.80),
    "antenna_white": (0.92, 0.92, 0.94),
    "antenna_rod": (0.80, 0.80, 0.82),
    "coil_copper": (0.72, 0.45, 0.20),
    "patch_copper": (0.72, 0.45, 0.20),
    "lens_dark": (0.08, 0.08, 0.10),
    "lens_barrel": (0.20, 0.20, 0.22),
    "camera_box": (0.30, 0.30, 0.32),
    "gps_white": (0.90, 0.90, 0.88),
    "substrate_green": (0.0, 0.40, 0.12),
}


def _c(name: str) -> str:
    """Return a FreeCAD tuple string for a named colour."""
    r, g, b = _COLORS[name]
    return f"({r},{g},{b})"


# ---------------------------------------------------------------------------
# Code generation helpers
# ---------------------------------------------------------------------------


def _indent(code: str, level: int = 0) -> str:
    """Dedent a triple-quoted block and optionally add indent."""
    text = textwrap.dedent(code).strip()
    if level > 0:
        prefix = "    " * level
        text = "\n".join(prefix + line if line.strip() else line for line in text.splitlines())
    return text


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class FreecadCubesatBuilder:
    """Build a realistic CubeSat 3D model in FreeCAD via RPC.

    The builder connects to a running FreeCAD instance through the FreeCADMCP
    XML-RPC server and sends Python code for execution. All component
    geometry is created using FreeCAD Part primitives and boolean operations.

    Args:
        rpc_host: Hostname of the FreeCAD RPC server.
        rpc_port: Port of the FreeCAD RPC server.
    """

    def __init__(self, rpc_host: str = "localhost", rpc_port: int = 9875) -> None:
        self._fc = xmlrpc.client.ServerProxy(
            f"http://{rpc_host}:{rpc_port}", allow_none=True
        )

    # ------------------------------------------------------------------ #
    # Connection check
    # ------------------------------------------------------------------ #

    def is_connected(self) -> bool:
        """Test whether the FreeCAD RPC server is reachable.

        Returns:
            True if the server responds to a ping, False otherwise.
        """
        try:
            return bool(self._fc.ping())
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def build(self, design: CubeSatDesign) -> FreecadModelResult:
        """Create a full CubeSat assembly in FreeCAD.

        Args:
            design: A fully populated CubeSat design specification.

        Returns:
            A FreecadModelResult summarising what was created.

        Raises:
            ConnectionError: If the FreeCAD RPC server is not reachable.
            RuntimeError: If code execution inside FreeCAD reports an error.
        """
        if not self.is_connected():
            raise ConnectionError(
                "Cannot reach FreeCAD RPC server. Ensure FreeCAD is running "
                "and the MCP RPC server is started."
            )

        doc_name = design.mission_name.replace("-", "_").replace(" ", "_")
        dims = CUBESAT_DIMS_MM.get(design.sat_size, CUBESAT_DIMS_MM["1U"])
        dx, dy, dz = dims

        # Create the document
        self._fc.create_document(doc_name)

        # Collect all code sections, then execute in one batch
        code_sections: list[str] = []
        object_count = 0

        # -- Preamble -------------------------------------------------------
        code_sections.append(self._preamble(doc_name))

        # -- Structure frame ------------------------------------------------
        frame_code, frame_count = self._structure_frame(dx, dy, dz)
        code_sections.append(frame_code)
        object_count += frame_count

        # -- Internal PCB stack ---------------------------------------------
        z_cursor = PLATE_THICK + 3.0  # start above bottom plate + small gap
        pcb_x0 = PCB_INSET
        pcb_y0 = PCB_INSET

        # EPS board
        has_battery = False
        if "eps" in design.subsystems:
            code, count = self._pcb_board("EPS", pcb_x0, pcb_y0, z_cursor)
            code_sections.append(code)
            object_count += count
            z_cursor += STACK_SPACER

            # Battery pack
            batt_code, batt_count = self._battery_pack(
                dx, dy, z_cursor, design.battery_type
            )
            code_sections.append(batt_code)
            object_count += batt_count
            has_battery = True
            z_cursor += 70.0  # battery height ~65mm + gap

        # OBC board
        if "obc" in design.subsystems:
            code, count = self._pcb_board("OBC", pcb_x0, pcb_y0, z_cursor)
            code_sections.append(code)
            object_count += count
            z_cursor += STACK_SPACER

        # COM UHF board
        if "com_uhf" in design.subsystems:
            code, count = self._pcb_board("COM_UHF", pcb_x0, pcb_y0, z_cursor)
            code_sections.append(code)
            object_count += count
            z_cursor += STACK_SPACER

        # COM S-Band board
        has_sband = "com_sband" in design.subsystems
        if has_sband:
            code, count = self._pcb_board("COM_SBAND", pcb_x0, pcb_y0, z_cursor)
            code_sections.append(code)
            object_count += count
            z_cursor += STACK_SPACER

        # ADCS board
        if "adcs" in design.subsystems:
            code, count = self._pcb_board("ADCS", pcb_x0, pcb_y0, z_cursor)
            code_sections.append(code)
            object_count += count
            z_cursor += STACK_SPACER

        # GPS receiver (small board)
        has_gps = "gps" in design.subsystems
        if has_gps:
            code, count = self._gps_antenna(dx, dy, dz)
            code_sections.append(code)
            object_count += count

        # -- Payload --------------------------------------------------------
        payload_code, payload_count = self._payload(
            design.payload_type, dx, dy, z_cursor, dz
        )
        code_sections.append(payload_code)
        object_count += payload_count

        # -- Solar panels ---------------------------------------------------
        has_solar = False
        if design.solar_config.startswith("Deployable"):
            panel_count_str = design.solar_config.split()[-1]  # "2-panel" or "4-panel"
            n_panels = 4 if "4" in panel_count_str else 2
            solar_code, solar_count = self._solar_panels(dx, dy, dz, n_panels)
            code_sections.append(solar_code)
            object_count += solar_count
            has_solar = True

        # -- UHF Antenna ----------------------------------------------------
        has_uhf_antenna = False
        if "com_uhf" in design.subsystems:
            ant_code, ant_count = self._uhf_antenna(dx, dy, dz)
            code_sections.append(ant_code)
            object_count += ant_count
            has_uhf_antenna = True

        # -- S-Band patch antenna -------------------------------------------
        has_sband_antenna = False
        if has_sband:
            sb_code, sb_count = self._sband_patch_antenna(dx, dy, dz)
            code_sections.append(sb_code)
            object_count += sb_count
            has_sband_antenna = True

        # -- Finalize -------------------------------------------------------
        code_sections.append(self._finalize())

        full_code = "\n\n".join(code_sections)
        result = self._fc.execute_code(full_code)

        if isinstance(result, dict) and not result.get("success", False):
            error_msg = result.get("error", "Unknown error")
            raise RuntimeError(f"FreeCAD code execution failed: {error_msg}")

        logger.info(
            "FreeCAD model '%s' created with ~%d objects",
            doc_name,
            object_count,
        )

        return FreecadModelResult(
            document_name=doc_name,
            object_count=object_count,
            has_solar_panels=has_solar,
            has_antenna=has_uhf_antenna or has_sband_antenna,
        )

    # ================================================================== #
    # Code generators for each component type
    # ================================================================== #

    @staticmethod
    def _preamble(doc_name: str) -> str:
        """Import statements and document reference."""
        return _indent(f"""
            import FreeCAD
            import Part
            import math
            doc = FreeCAD.getDocument("{doc_name}")

            def _set_color(obj, rgb, transparency=0):
                obj.ViewObject.ShapeColor = rgb
                if transparency > 0:
                    obj.ViewObject.Transparency = transparency

            def _make_part(name, shape, rgb, transparency=0):
                obj = doc.addObject("Part::Feature", name)
                obj.Shape = shape
                _set_color(obj, rgb, transparency)
                return obj
        """)

    @staticmethod
    def _finalize() -> str:
        """Recompute and set view."""
        return _indent("""
            doc.recompute()
            try:
                FreeCADGui.ActiveDocument.ActiveView.fitAll()
                FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
            except Exception:
                pass
        """)

    # ------------------------------------------------------------------ #
    # 1. Structure Frame
    # ------------------------------------------------------------------ #

    @staticmethod
    def _structure_frame(
        dx: float, dy: float, dz: float
    ) -> tuple[str, int]:
        """Generate code for the CubeSat structure frame.

        Creates 4 corner L-profile rails, top and bottom plates with
        mounting holes.

        Returns:
            Tuple of (code_string, object_count).
        """
        leg = RAIL_LEG
        t = RAIL_THICK
        pt = PLATE_THICK
        hole_d = MOUNTING_HOLE_D
        inset = MOUNTING_HOLE_INSET
        fc = _c("frame_gray")
        pc = _c("plate_gray")

        # Corner positions and rotation angles for L-profile rails
        # Each corner: (x_offset, y_offset, rotation_deg_around_z)
        corners = [
            (0.0, 0.0, 0.0),
            (dx, 0.0, 90.0),
            (dx, dy, 180.0),
            (0.0, dy, 270.0),
        ]

        code = f"""
# === STRUCTURE FRAME ===
# Corner rail L-profile cross section
rail_leg = {leg}
rail_t = {t}
dz = {dz}

rail_shapes = []
for cx, cy, angle in {corners}:
    # Create L-profile as two intersecting rectangles
    vert_box = Part.makeBox(rail_leg, rail_t, dz)
    horiz_box = Part.makeBox(rail_t, rail_leg, dz)
    l_profile = vert_box.fuse(horiz_box)
    # Rotate around z-axis at corner
    l_profile.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), angle)
    l_profile.translate(FreeCAD.Vector(cx, cy, 0))
    rail_shapes.append(l_profile)

rails_compound = Part.makeCompound(rail_shapes)
_make_part("Structure_Rails", rails_compound, {fc}, 60)

# Bottom plate with mounting holes
plate_w = {dx}
plate_d = {dy}
plate_t = {pt}
bottom_plate = Part.makeBox(plate_w, plate_d, plate_t)

# Drill mounting holes in bottom plate
hole_r = {hole_d / 2.0}
inset = {inset}
hole_positions = [
    (inset, inset),
    (plate_w - inset, inset),
    (plate_w - inset, plate_d - inset),
    (inset, plate_d - inset),
    (plate_w / 2.0, inset),
    (plate_w / 2.0, plate_d - inset),
    (inset, plate_d / 2.0),
    (plate_w - inset, plate_d / 2.0),
]
for hx, hy in hole_positions:
    hole_cyl = Part.makeCylinder(hole_r, plate_t * 2, FreeCAD.Vector(hx, hy, -0.5))
    bottom_plate = bottom_plate.cut(hole_cyl)

_make_part("Bottom_Plate", bottom_plate, {pc}, 40)

# Top plate (same pattern, at top)
top_plate = Part.makeBox(plate_w, plate_d, plate_t)
top_plate.translate(FreeCAD.Vector(0, 0, {dz} - plate_t))
for hx, hy in hole_positions:
    hole_cyl = Part.makeCylinder(hole_r, plate_t * 2, FreeCAD.Vector(hx, hy, {dz} - plate_t - 0.5))
    top_plate = top_plate.cut(hole_cyl)

_make_part("Top_Plate", top_plate, {pc}, 40)
"""
        return _indent(code), 3  # rails + bottom_plate + top_plate

    # ------------------------------------------------------------------ #
    # 2. PCB Boards
    # ------------------------------------------------------------------ #

    @staticmethod
    def _pcb_board(
        name: str, x0: float, y0: float, z0: float
    ) -> tuple[str, int]:
        """Generate code for a PCB board with IC components and pin headers.

        Args:
            name: Label for the board (e.g. "EPS", "OBC").
            x0: X position of the board.
            y0: Y position of the board.
            z0: Z position (bottom of PCB).

        Returns:
            Tuple of (code_string, object_count).
        """
        w = PCB_WIDTH
        d = PCB_DEPTH
        t = PCB_THICK
        gc = _c("pcb_green")
        ic_c = _c("ic_black")
        pin_c = _c("pin_gold")

        code = f"""
# === PCB: {name} ===
pcb_{name} = Part.makeBox({w}, {d}, {t})
pcb_{name}.translate(FreeCAD.Vector({x0}, {y0}, {z0}))
_make_part("PCB_{name}", pcb_{name}, {gc})

# IC chips on {name}
ic_shapes_{name} = []
ic_positions = [
    ({x0 + 15}, {y0 + 15}, {z0 + t}),
    ({x0 + 50}, {y0 + 15}, {z0 + t}),
    ({x0 + 15}, {y0 + 50}, {z0 + t}),
    ({x0 + 50}, {y0 + 50}, {z0 + t}),
    ({x0 + 35}, {y0 + 35}, {z0 + t}),
]
ic_sizes = [
    (12, 12, 2.5),
    (8, 8, 1.8),
    (10, 10, 2.0),
    (6, 6, 1.5),
    (14, 14, 3.0),
]
for (ix, iy, iz), (iw, id_, ih) in zip(ic_positions, ic_sizes):
    ic = Part.makeBox(iw, id_, ih)
    ic.translate(FreeCAD.Vector(ix, iy, iz))
    ic_shapes_{name}.append(ic)

if ic_shapes_{name}:
    ic_compound = Part.makeCompound(ic_shapes_{name})
    _make_part("ICs_{name}", ic_compound, {ic_c})

# Pin headers on {name} (along one edge)
pin_shapes_{name} = []
for i in range(8):
    pin = Part.makeBox(2.54, 2.54, 8.5)
    pin.translate(FreeCAD.Vector({x0 + 5 + 2.54 * 1.5} + i * 5.08, {y0 + d - 5}, {z0 - 6.0}))
    pin_shapes_{name}.append(pin)

for i in range(8):
    pin = Part.makeBox(2.54, 2.54, 8.5)
    pin.translate(FreeCAD.Vector({x0 + 5 + 2.54 * 1.5} + i * 5.08, {y0 + 1.0}, {z0 - 6.0}))
    pin_shapes_{name}.append(pin)

if pin_shapes_{name}:
    pin_compound = Part.makeCompound(pin_shapes_{name})
    _make_part("Pins_{name}", pin_compound, {pin_c})
"""
        return _indent(code), 3  # pcb + ics + pins

    # ------------------------------------------------------------------ #
    # 3. Battery Pack
    # ------------------------------------------------------------------ #

    @staticmethod
    def _battery_pack(
        dx: float, dy: float, z0: float, battery_type: str
    ) -> tuple[str, int]:
        """Generate code for a battery pack.

        For Li-ion 18650: two cylindrical cells side by side wrapped in
        kapton with a holder frame. For other types: a rectangular pouch.

        Returns:
            Tuple of (code_string, object_count).
        """
        bc = _c("battery_amber")
        hc = _c("battery_holder")

        if "18650" in battery_type:
            cell_r = 9.0  # mm radius
            cell_h = 65.0  # mm height
            # Centre the pair in the frame
            cx = dx / 2.0
            cy = dy / 2.0
            gap = 1.0
            x1 = cx - cell_r - gap / 2.0
            x2 = cx + gap / 2.0 + cell_r

            code = f"""
# === BATTERY PACK (18650 x2) ===
cell1 = Part.makeCylinder({cell_r}, {cell_h}, FreeCAD.Vector({x1}, {cy}, {z0}))
cell2 = Part.makeCylinder({cell_r}, {cell_h}, FreeCAD.Vector({x2}, {cy}, {z0}))
batt_cells = Part.makeCompound([cell1, cell2])
_make_part("Battery_Cells", batt_cells, {bc})

# Battery holder frame
holder_w = {cell_r * 2 * 2 + gap + 4}
holder_d = {cell_r * 2 + 4}
holder_h = 5.0
holder_x = {cx} - holder_w / 2.0
holder_y = {cy} - holder_d / 2.0

bottom_holder = Part.makeBox(holder_w, holder_d, holder_h)
bottom_holder.translate(FreeCAD.Vector(holder_x, holder_y, {z0}))
top_holder = Part.makeBox(holder_w, holder_d, holder_h)
top_holder.translate(FreeCAD.Vector(holder_x, holder_y, {z0 + cell_h - 5.0}))
holder_compound = Part.makeCompound([bottom_holder, top_holder])
_make_part("Battery_Holder", holder_compound, {hc})
"""
            return _indent(code), 2  # cells + holder
        else:
            # Pouch / prismatic battery
            bw = 70.0
            bd = 50.0
            bh = 12.0
            bx = (dx - bw) / 2.0
            by = (dy - bd) / 2.0
            code = f"""
# === BATTERY PACK (Pouch) ===
pouch = Part.makeBox({bw}, {bd}, {bh})
pouch.translate(FreeCAD.Vector({bx}, {by}, {z0}))
_make_part("Battery_Pouch", pouch, {bc})
"""
            return _indent(code), 1

    # ------------------------------------------------------------------ #
    # 4. Solar Panels (deployable)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _solar_panels(
        dx: float, dy: float, dz: float, n_panels: int
    ) -> tuple[str, int]:
        """Generate code for deployable solar panels.

        Creates thin dark-blue panels with hinge cylinders and solar cell
        grid lines. Panels are deployed at a 30-degree angle from the body.

        Returns:
            Tuple of (code_string, object_count).
        """
        panel_w = dx - 4.0  # slightly narrower than body
        panel_h = dz - 10.0  # slightly shorter than body
        panel_t = 2.0
        hinge_r = 2.5
        hinge_h = 8.0
        deploy_angle = 30.0

        sc = _c("solar_blue")
        hc = _c("hinge_silver")
        lc = _c("solar_cell_line")

        code = f"""
# === SOLAR PANELS (Deployable, {n_panels} panels) ===
panel_w = {panel_w}
panel_h = {panel_h}
panel_t = {panel_t}
deploy_angle = {deploy_angle}
"""

        if n_panels >= 2:
            # Left and right panels
            code += f"""
# Left panel
left_panel = Part.makeBox(panel_w, panel_t, panel_h)

# Solar cell grid lines on left panel (horizontal lines)
left_lines = []
for i in range(1, 8):
    line = Part.makeBox(panel_w - 2, 0.3, 0.3)
    line.translate(FreeCAD.Vector(1, -0.15, i * panel_h / 8.0))
    left_lines.append(line)
# Vertical lines
for i in range(1, 6):
    line = Part.makeBox(0.3, 0.3, panel_h - 2)
    line.translate(FreeCAD.Vector(i * panel_w / 6.0, -0.15, 1))
    left_lines.append(line)

left_panel_shape = left_panel.fuse(Part.makeCompound(left_lines)) if left_lines else left_panel

# Hinge at left attachment
left_hinge = Part.makeCylinder({hinge_r}, {hinge_h}, FreeCAD.Vector(panel_w / 2 - {hinge_h / 2}, 0, 0), FreeCAD.Vector(1, 0, 0))

# Position: rotate to deploy angle, place on left side
left_panel_shape.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 90 + deploy_angle)
left_panel_shape.translate(FreeCAD.Vector(-2, {dy / 2.0}, 5))
left_hinge.translate(FreeCAD.Vector(-2, {dy / 2.0}, 5))

_make_part("Solar_Left", left_panel_shape, {sc})
_make_part("Hinge_Left", left_hinge, {hc})

# Right panel (mirror)
right_panel = Part.makeBox(panel_w, panel_t, panel_h)

right_lines = []
for i in range(1, 8):
    line = Part.makeBox(panel_w - 2, 0.3, 0.3)
    line.translate(FreeCAD.Vector(1, -0.15, i * panel_h / 8.0))
    right_lines.append(line)
for i in range(1, 6):
    line = Part.makeBox(0.3, 0.3, panel_h - 2)
    line.translate(FreeCAD.Vector(i * panel_w / 6.0, -0.15, 1))
    right_lines.append(line)

right_panel_shape = right_panel.fuse(Part.makeCompound(right_lines)) if right_lines else right_panel

right_hinge = Part.makeCylinder({hinge_r}, {hinge_h}, FreeCAD.Vector(panel_w / 2 - {hinge_h / 2}, 0, 0), FreeCAD.Vector(1, 0, 0))

right_panel_shape.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), -(90 + deploy_angle))
right_panel_shape.translate(FreeCAD.Vector({dx + 2}, {dy / 2.0}, 5))
right_hinge.translate(FreeCAD.Vector({dx + 2}, {dy / 2.0}, 5))

_make_part("Solar_Right", right_panel_shape, {sc})
_make_part("Hinge_Right", right_hinge, {hc})
"""
            obj_count = 4  # 2 panels + 2 hinges

        if n_panels == 4:
            code += f"""
# Front and back panels
front_panel = Part.makeBox(panel_t, {dy - 4}, panel_h)
front_lines = []
for i in range(1, 8):
    line = Part.makeBox(0.3, {dy - 6}, 0.3)
    line.translate(FreeCAD.Vector(-0.15, 1, i * panel_h / 8.0))
    front_lines.append(line)
front_panel_shape = front_panel.fuse(Part.makeCompound(front_lines)) if front_lines else front_panel
front_hinge = Part.makeCylinder({hinge_r}, {hinge_h}, FreeCAD.Vector(0, {dy / 2 - hinge_h / 2}, 0), FreeCAD.Vector(0, 1, 0))

front_panel_shape.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), deploy_angle)
front_panel_shape.translate(FreeCAD.Vector({dx / 2.0}, -2, 5))
front_hinge.translate(FreeCAD.Vector({dx / 2.0}, -2, 5))

_make_part("Solar_Front", front_panel_shape, {sc})
_make_part("Hinge_Front", front_hinge, {hc})

# Back panel
back_panel = Part.makeBox(panel_t, {dy - 4}, panel_h)
back_lines = []
for i in range(1, 8):
    line = Part.makeBox(0.3, {dy - 6}, 0.3)
    line.translate(FreeCAD.Vector(-0.15, 1, i * panel_h / 8.0))
    back_lines.append(line)
back_panel_shape = back_panel.fuse(Part.makeCompound(back_lines)) if back_lines else back_panel
back_hinge = Part.makeCylinder({hinge_r}, {hinge_h}, FreeCAD.Vector(0, {dy / 2 - hinge_h / 2}, 0), FreeCAD.Vector(0, 1, 0))

back_panel_shape.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), -deploy_angle)
back_panel_shape.translate(FreeCAD.Vector({dx / 2.0}, {dy + 2}, 5))
back_hinge.translate(FreeCAD.Vector({dx / 2.0}, {dy + 2}, 5))

_make_part("Solar_Back", back_panel_shape, {sc})
_make_part("Hinge_Back", back_hinge, {hc})
"""
            obj_count = 8  # 4 panels + 4 hinges

        return _indent(code), obj_count

    # ------------------------------------------------------------------ #
    # 5. UHF Antenna (deployable monopole)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _uhf_antenna(dx: float, dy: float, dz: float) -> tuple[str, int]:
        """Generate code for a deployable UHF monopole antenna.

        Creates 4 thin rods at 45-degree angles from the top face with
        small coil springs at the base.

        Returns:
            Tuple of (code_string, object_count).
        """
        rod_r = 0.5  # mm
        rod_len = 170.0  # mm (~quarter wavelength at 437 MHz)
        coil_r = 3.0
        coil_h = 6.0
        rod_angle = 45.0  # degrees from vertical
        rc = _c("antenna_rod")
        cc = _c("coil_copper")

        cx = dx / 2.0
        cy = dy / 2.0

        code = f"""
# === UHF ANTENNA (4x Deployable Monopole) ===
rod_r = {rod_r}
rod_len = {rod_len}
rod_angle = {rod_angle}
top_z = {dz}
cx = {cx}
cy = {cy}

rod_shapes = []
coil_shapes = []

# 4 rods at 45 deg, pointing outward in 4 diagonal directions
offsets = [
    (1, 1),   # +X +Y
    (1, -1),  # +X -Y
    (-1, 1),  # -X +Y
    (-1, -1), # -X -Y
]

for ox, oy in offsets:
    # Coil at base
    coil = Part.makeCylinder({coil_r}, {coil_h}, FreeCAD.Vector(cx + ox * 15, cy + oy * 15, top_z))
    coil_shapes.append(coil)

    # Rod: cylinder angled at 45 deg
    rod = Part.makeCylinder(rod_r, rod_len, FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1))
    # Tilt 45 degrees
    tilt_axis = FreeCAD.Vector(-oy, ox, 0).normalize()
    rod.rotate(FreeCAD.Vector(0, 0, 0), tilt_axis, rod_angle)
    rod.translate(FreeCAD.Vector(cx + ox * 15, cy + oy * 15, top_z + {coil_h}))
    rod_shapes.append(rod)

rods_compound = Part.makeCompound(rod_shapes)
_make_part("UHF_Antenna_Rods", rods_compound, {rc})

coils_compound = Part.makeCompound(coil_shapes)
_make_part("UHF_Antenna_Coils", coils_compound, {cc})
"""
        return _indent(code), 2  # rods + coils

    # ------------------------------------------------------------------ #
    # 6. S-Band Patch Antenna
    # ------------------------------------------------------------------ #

    @staticmethod
    def _sband_patch_antenna(
        dx: float, dy: float, dz: float
    ) -> tuple[str, int]:
        """Generate code for an S-band patch antenna on the top face.

        Creates a square copper patch on a PCB substrate.

        Returns:
            Tuple of (code_string, object_count).
        """
        patch_w = 40.0
        patch_d = 40.0
        patch_t = 0.5
        sub_w = 50.0
        sub_d = 50.0
        sub_t = 1.6

        pc = _c("patch_copper")
        sc = _c("substrate_green")

        cx = dx / 2.0
        cy = dy / 2.0

        code = f"""
# === S-BAND PATCH ANTENNA ===
# Substrate (PCB)
sub_x = {cx - sub_w / 2.0}
sub_y = {cy - sub_d / 2.0}
sub_z = {dz}
substrate = Part.makeBox({sub_w}, {sub_d}, {sub_t})
substrate.translate(FreeCAD.Vector(sub_x, sub_y, sub_z))
_make_part("SBand_Substrate", substrate, {sc})

# Copper patch
patch_x = {cx - patch_w / 2.0}
patch_y = {cy - patch_d / 2.0}
patch_z = {dz + sub_t}
patch = Part.makeBox({patch_w}, {patch_d}, {patch_t})
patch.translate(FreeCAD.Vector(patch_x, patch_y, patch_z))
_make_part("SBand_Patch", patch, {pc})
"""
        return _indent(code), 2  # substrate + patch

    # ------------------------------------------------------------------ #
    # 7. Payload (Camera / SDR / generic)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _payload(
        payload_type: str,
        dx: float,
        dy: float,
        z0: float,
        dz: float,
    ) -> tuple[str, int]:
        """Generate code for the payload module.

        For Camera: lens barrel + electronics box + lens element.
        For other types: generic module box with a label.

        Returns:
            Tuple of (code_string, object_count).
        """
        cx = dx / 2.0
        cy = dy / 2.0
        lc = _c("lens_dark")
        bc = _c("lens_barrel")
        ec = _c("camera_box")

        if "Camera" in payload_type or "EO" in payload_type:
            barrel_r = 15.0
            barrel_h = 50.0
            box_w = 50.0
            box_d = 50.0
            box_h = 30.0
            lens_r = 12.0
            lens_t = 2.0

            code = f"""
# === PAYLOAD: Camera (EO) ===
# Electronics box
cam_box = Part.makeBox({box_w}, {box_d}, {box_h})
cam_box.translate(FreeCAD.Vector({cx - box_w / 2.0}, {cy - box_d / 2.0}, {z0}))
_make_part("Camera_Electronics", cam_box, {ec})

# Lens barrel (cylinder on top of electronics)
barrel = Part.makeCylinder({barrel_r}, {barrel_h}, FreeCAD.Vector({cx}, {cy}, {z0 + box_h}))
_make_part("Camera_Barrel", barrel, {bc})

# Lens element (dark disc on top of barrel)
lens = Part.makeCylinder({lens_r}, {lens_t}, FreeCAD.Vector({cx}, {cy}, {z0 + box_h + barrel_h}))
_make_part("Camera_Lens", lens, {lc})

# Lens ring (outer ring around lens)
lens_ring = Part.makeCylinder({barrel_r}, {lens_t}, FreeCAD.Vector({cx}, {cy}, {z0 + box_h + barrel_h}))
lens_cutout = Part.makeCylinder({lens_r}, {lens_t + 1}, FreeCAD.Vector({cx}, {cy}, {z0 + box_h + barrel_h - 0.5}))
lens_ring = lens_ring.cut(lens_cutout)
_make_part("Camera_Lens_Ring", lens_ring, {bc})
"""
            return _indent(code), 4
        else:
            # Generic payload module
            pw = min(80.0, dx - 2 * PCB_INSET)
            pd = min(80.0, dy - 2 * PCB_INSET)
            ph = 25.0

            gc = _c("ic_black")
            code = f"""
# === PAYLOAD: {payload_type} ===
payload_box = Part.makeBox({pw}, {pd}, {ph})
payload_box.translate(FreeCAD.Vector({cx - pw / 2.0}, {cy - pd / 2.0}, {z0}))
_make_part("Payload_Module", payload_box, {gc})

# Connector strip
conn = Part.makeBox({pw - 10}, 5, 3)
conn.translate(FreeCAD.Vector({cx - (pw - 10) / 2.0}, {cy - pd / 2.0 + 2}, {z0 + ph}))
_make_part("Payload_Connector", conn, {_c("pin_gold")})
"""
            return _indent(code), 2

    # ------------------------------------------------------------------ #
    # 8. GPS Antenna
    # ------------------------------------------------------------------ #

    @staticmethod
    def _gps_antenna(
        dx: float, dy: float, dz: float
    ) -> tuple[str, int]:
        """Generate code for a GPS ceramic patch antenna on the top face.

        Returns:
            Tuple of (code_string, object_count).
        """
        patch_w = 25.0
        patch_d = 25.0
        patch_h = 4.0
        gc = _c("gps_white")
        sc = _c("substrate_green")

        # Place it offset from centre to avoid collision with S-band patch
        px = dx * 0.25
        py = dy * 0.75

        code = f"""
# === GPS PATCH ANTENNA ===
# PCB substrate
gps_sub = Part.makeBox(30, 30, 1.0)
gps_sub.translate(FreeCAD.Vector({px - 15}, {py - 15}, {dz}))
_make_part("GPS_Substrate", gps_sub, {sc})

# Ceramic patch
gps_patch = Part.makeBox({patch_w}, {patch_d}, {patch_h})
gps_patch.translate(FreeCAD.Vector({px - patch_w / 2.0}, {py - patch_d / 2.0}, {dz + 1.0}))
_make_part("GPS_Patch", gps_patch, {gc})
"""
        return _indent(code), 2  # substrate + patch


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------


def _demo() -> None:
    """Build a demo CubeSat model in FreeCAD for quick validation."""
    design = CubeSatDesign(
        mission_name="DemoSat-1",
        sat_size="3U",
        orbit_type="SSO",
        orbit_altitude=550,
        orbit_inclination=97.6,
        design_life=3,
        payload_type="Camera (EO)",
        payload_power=8.0,
        payload_mass=350,
        subsystems=["eps", "obc", "com_uhf", "com_sband", "adcs", "gps"],
        solar_config="Deployable 2-panel",
        battery_type="Li-ion 18650",
        data_budget=500,
    )

    builder = FreecadCubesatBuilder()
    if not builder.is_connected():
        print("ERROR: FreeCAD RPC server is not running.")
        print("Start it in FreeCAD Python console:")
        print('  exec(open("C:/Users/Mustafa/AppData/Roaming/FreeCAD/Mod/FreeCADMCP/start_rpc.py").read())')
        return

    result = builder.build(design)
    print(f"Document : {result.document_name}")
    print(f"Objects  : {result.object_count}")
    print(f"Solar    : {result.has_solar_panels}")
    print(f"Antenna  : {result.has_antenna}")


if __name__ == "__main__":
    _demo()
