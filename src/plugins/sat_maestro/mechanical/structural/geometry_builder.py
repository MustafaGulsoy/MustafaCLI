"""Parametric 3D CubeSat geometry builder using the Gmsh OCC kernel.

Creates a hollow aluminium shell with internally stacked component
volumes, fragments them for a conformal mesh, assigns physical groups,
and exports a STEP file.  No FreeCAD dependency -- pure Gmsh Python API.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import gmsh
except ImportError:
    gmsh = None  # type: ignore[assignment]

from ...cubesat_wizard import CubeSatDesign
from .materials import COMPONENT_MATERIALS, DEFAULT_MATERIAL_KEY, MATERIALS

# ---------------------------------------------------------------------------
# Dimensional constants
# ---------------------------------------------------------------------------

CUBESAT_DIMENSIONS: dict[str, tuple[float, float, float]] = {
    # (width_x, depth_y, height_z) in metres
    "1U": (0.1, 0.1, 0.1),
    "2U": (0.1, 0.1, 0.2),
    "3U": (0.1, 0.1, 0.3),
    "6U": (0.2, 0.1, 0.3),
    "12U": (0.2, 0.2, 0.3),
}

WALL_THICKNESS: float = 0.0015  # 1.5 mm Al-7075 walls
INTERNAL_GAP: float = 0.001  # 1 mm gap between components and walls
INTER_COMP_GAP: float = 0.0005  # 0.5 mm gap between stacked components


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class GeometryResult:
    """Outcome of a geometry build operation.

    Attributes:
        step_file: Absolute path to the exported STEP file.
        component_volumes: Mapping from component ``id`` to its list of
            gmsh volume tags after fragmentation.
        structure_volume_tags: Gmsh volume tags that belong to the
            structural shell after fragmentation.
        bottom_surface_tags: Surface tags at z ~ 0 (for boundary conditions).
        total_volumes: Total number of 3-D volumes in the model.
        bounding_box: ``(xmin, ymin, zmin, xmax, ymax, zmax)`` of the
            full assembly.
    """

    step_file: str
    component_volumes: dict[str, list[int]]
    structure_volume_tags: list[int]
    bottom_surface_tags: list[int]
    total_volumes: int
    bounding_box: tuple[float, float, float, float, float, float]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class CubesatGeometryBuilder:
    """Build a parametric CubeSat 3-D model from a :class:`CubeSatDesign`.

    The workflow is:

    1. Create a hollow shell (outer box minus inner cavity).
    2. Stack component blocks inside the cavity along the Z axis.
    3. Fragment all volumes to produce a conformal topology.
    4. Identify renumbered volumes and assign physical groups.
    5. Identify the bottom face(s) for boundary-condition application.
    6. Export the model to STEP format.
    """

    def __init__(self, design: CubeSatDesign) -> None:
        self._design = design

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def build(self, output_dir: Path | str, *, twin: bool = False) -> GeometryResult:
        """Build geometry and export STEP.

        Args:
            output_dir: Directory where the ``<mission_name>.step`` file
                will be written.  Created if it does not exist.
            twin: If True, create a second identical copy placed next to
                the first one along the X axis (digital twin visualisation).

        Returns:
            A :class:`GeometryResult` with all tags and paths.

        Raises:
            ImportError: If the ``gmsh`` package is not installed.
            ValueError: If the satellite size is not recognised.
        """
        if gmsh is None:
            raise ImportError(
                "gmsh package is required. Install with: pip install gmsh"
            )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        dims = CUBESAT_DIMENSIONS.get(self._design.sat_size)
        if dims is None:
            raise ValueError(
                f"Unknown CubeSat size '{self._design.sat_size}'. "
                f"Supported: {list(CUBESAT_DIMENSIONS)}"
            )

        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)  # suppress console spam
        gmsh.model.add(self._design.mission_name)

        try:
            result = self._build_inner(dims, output_dir, twin=twin)
        finally:
            gmsh.finalize()

        return result

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _build_inner(
        self,
        dims: tuple[float, float, float],
        output_dir: Path,
        *,
        twin: bool = False,
    ) -> GeometryResult:
        """Core geometry construction (called between init/finalize)."""
        wt = WALL_THICKNESS
        dx, dy, dz = dims

        # ---- 1. Outer and inner boxes -> hollow shell ----
        outer_tag = gmsh.model.occ.addBox(0, 0, 0, dx, dy, dz)
        inner_tag = gmsh.model.occ.addBox(
            wt, wt, wt,
            dx - 2 * wt, dy - 2 * wt, dz - 2 * wt,
        )
        shell_dimtags, _shell_map = gmsh.model.occ.cut(
            [(3, outer_tag)], [(3, inner_tag)], removeObject=True, removeTool=True
        )
        if not shell_dimtags:
            raise RuntimeError("OCC boolean cut produced no volumes for shell")
        structure_tag = shell_dimtags[0][1]
        logger.debug("Shell structure tag: %d", structure_tag)

        # ---- 2. Internal component blocks ----
        all_components = self._design.get_all_components()
        internal_comps = [c for c in all_components if c["id"] != "structure_frame"]

        # Pre-fragment volume tag -> component id
        prefrag_comp_tags: dict[int, str] = {}

        if internal_comps:
            prefrag_comp_tags = self._stack_components(
                internal_comps, dims, wt,
            )

        # ---- 3. Fragment everything for conformal mesh ----
        all_object_dimtags = [(3, structure_tag)]
        all_tool_dimtags = [(3, t) for t in prefrag_comp_tags]

        if all_tool_dimtags:
            frag_dimtags, frag_map = gmsh.model.occ.fragment(
                all_object_dimtags, all_tool_dimtags,
            )
        else:
            # No internal components -- just synchronize
            frag_dimtags = all_object_dimtags
            frag_map = [all_object_dimtags]

        gmsh.model.occ.synchronize()

        # ---- 4. Identify volumes by bounding-box centre ----
        (
            comp_volume_map,
            struct_tags,
        ) = self._classify_volumes_after_fragment(
            prefrag_comp_tags, dims, wt, frag_map,
        )

        # ---- 5. Physical groups ----
        self._assign_physical_groups(struct_tags, comp_volume_map)

        # ---- 6. Find bottom surface(s) at z ~ 0 ----
        bottom_tags = self._find_bottom_surfaces()

        if bottom_tags:
            gmsh.model.addPhysicalGroup(2, bottom_tags, name="BC_bottom")
            logger.debug("Bottom BC surface tags: %s", bottom_tags)

        # ---- 7. Digital twin: duplicate entire model beside the original ----
        if twin:
            gap_between = dx * 0.5  # half-width gap between twins
            offset_x = dx + gap_between
            all_entities = gmsh.model.occ.getEntities()
            if all_entities:
                copied = gmsh.model.occ.copy(all_entities)
                gmsh.model.occ.translate(copied, offset_x, 0, 0)
                gmsh.model.occ.synchronize()
                logger.info("Digital twin created at x-offset %.4f m", offset_x)

        # ---- 8. Export STEP ----
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in self._design.mission_name
        )
        suffix = "_twin" if twin else ""
        step_path = str(output_dir / f"{safe_name}{suffix}.step")
        gmsh.write(step_path)
        logger.info("STEP file written to %s", step_path)

        # ---- 8. Collect summary stats ----
        all_vols = gmsh.model.getEntities(dim=3)
        bbox = gmsh.model.getBoundingBox(-1, -1)  # whole model

        return GeometryResult(
            step_file=step_path,
            component_volumes=comp_volume_map,
            structure_volume_tags=struct_tags,
            bottom_surface_tags=bottom_tags,
            total_volumes=len(all_vols),
            bounding_box=(bbox[0], bbox[1], bbox[2], bbox[3], bbox[4], bbox[5]),
        )

    # ------------------------------------------------------------------ #

    def _stack_components(
        self,
        components: list[dict[str, Any]],
        dims: tuple[float, float, float],
        wt: float,
    ) -> dict[int, str]:
        """Create stacked component boxes inside the cavity.

        Returns a mapping of pre-fragment volume tags to component IDs.
        """
        dx, dy, dz = dims
        gap = INTERNAL_GAP

        cavity_x0 = wt + gap
        cavity_y0 = wt + gap
        cavity_width = dx - 2 * wt - 2 * gap
        cavity_depth = dy - 2 * wt - 2 * gap
        available_height = dz - 2 * wt - 2 * gap

        if cavity_width <= 0 or cavity_depth <= 0 or available_height <= 0:
            logger.warning(
                "Cavity dimensions non-positive (%.4f, %.4f, %.4f). "
                "No internal components will be placed.",
                cavity_width,
                cavity_depth,
                available_height,
            )
            return {}

        total_mass = sum(c["mass_g"] for c in components)
        if total_mass <= 0:
            total_mass = 1.0  # avoid division by zero

        # Reserve 10 % of cavity height for inter-component gaps
        usable_height = available_height * 0.90
        total_gap_space = available_height * 0.10

        n_gaps = max(len(components) - 1, 1)
        per_gap = total_gap_space / n_gaps

        z_cursor = wt + gap
        tag_map: dict[int, str] = {}

        for comp in components:
            height = max(0.005, (comp["mass_g"] / total_mass) * usable_height)

            # Clamp so we don't overflow the cavity
            remaining = (wt + gap + available_height) - z_cursor
            if remaining <= 0:
                logger.warning(
                    "No cavity space left for component '%s'", comp["id"],
                )
                break
            height = min(height, remaining)

            vol_tag = gmsh.model.occ.addBox(
                cavity_x0, cavity_y0, z_cursor,
                cavity_width, cavity_depth, height,
            )
            tag_map[vol_tag] = comp["id"]
            logger.debug(
                "Component '%s': tag=%d  z=%.4f  h=%.4f",
                comp["id"], vol_tag, z_cursor, height,
            )
            z_cursor += height + per_gap

        return tag_map

    # ------------------------------------------------------------------ #

    def _classify_volumes_after_fragment(
        self,
        prefrag_comp_tags: dict[int, str],
        dims: tuple[float, float, float],
        wt: float,
        frag_map: list[list[tuple[int, int]]],
    ) -> tuple[dict[str, list[int]], list[int]]:
        """After fragment, identify which new tags are structure vs component.

        The ``frag_map`` produced by ``gmsh.model.occ.fragment`` has one
        entry per input entity (objects first, then tools). We use that
        mapping directly when available; if the mapping is ambiguous we
        fall back to bounding-box heuristics.

        Returns:
            (component_volumes, structure_volume_tags)
        """
        dx, dy, dz = dims
        gap = INTERNAL_GAP

        # frag_map[0] = children of structure (the object)
        # frag_map[1..N] = children of each tool (component) in order
        comp_volume_map: dict[str, list[int]] = {}
        all_comp_tags: set[int] = set()

        # Map from original tag -> component id, preserving insertion order
        ordered_comp_ids = list(prefrag_comp_tags.values())

        for i, comp_id in enumerate(ordered_comp_ids):
            map_idx = i + 1  # offset by 1 because index 0 is the structure
            if map_idx < len(frag_map):
                child_tags = [t for _, t in frag_map[map_idx]]
            else:
                child_tags = []

            if comp_id not in comp_volume_map:
                comp_volume_map[comp_id] = []
            comp_volume_map[comp_id].extend(child_tags)
            all_comp_tags.update(child_tags)

        # Structure tags are everything in frag_map[0] that is NOT a comp tag
        struct_tags: list[int] = []
        if frag_map:
            for _, t in frag_map[0]:
                if t not in all_comp_tags:
                    struct_tags.append(t)

        # If no structure tags found via map, fall back to BBox heuristic
        if not struct_tags:
            struct_tags = self._identify_structure_by_bbox(
                all_comp_tags, dx, dy, dz, wt,
            )

        return comp_volume_map, struct_tags

    # ------------------------------------------------------------------ #

    def _identify_structure_by_bbox(
        self,
        known_comp_tags: set[int],
        dx: float,
        dy: float,
        dz: float,
        wt: float,
    ) -> list[int]:
        """Fallback: identify structure volumes by checking their BBox.

        A volume whose bounding box spans nearly the full satellite
        envelope is likely part of the structural shell.
        """
        struct_tags: list[int] = []
        all_vols = gmsh.model.getEntities(dim=3)
        tol = wt * 0.5

        for _, tag in all_vols:
            if tag in known_comp_tags:
                continue
            xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(3, tag)
            span_x = xmax - xmin
            span_y = ymax - ymin
            span_z = zmax - zmin

            # The shell should span close to the full satellite in at least
            # two dimensions.
            full_dims = 0
            if abs(span_x - dx) < tol:
                full_dims += 1
            if abs(span_y - dy) < tol:
                full_dims += 1
            if abs(span_z - dz) < tol:
                full_dims += 1

            if full_dims >= 2:
                struct_tags.append(tag)

        # If heuristic fails, collect all non-component volumes
        if not struct_tags:
            struct_tags = [
                t for _, t in all_vols if t not in known_comp_tags
            ]

        return struct_tags

    # ------------------------------------------------------------------ #

    def _assign_physical_groups(
        self,
        structure_tags: list[int],
        comp_map: dict[str, list[int]],
    ) -> None:
        """Create named physical groups for each domain."""
        if structure_tags:
            mat_key = COMPONENT_MATERIALS.get("structure_frame", "AL7075")
            gmsh.model.addPhysicalGroup(
                3, structure_tags, name=f"structure_{mat_key}",
            )

        for comp_id, tags in comp_map.items():
            if not tags:
                continue
            mat_key = COMPONENT_MATERIALS.get(comp_id, DEFAULT_MATERIAL_KEY)
            gmsh.model.addPhysicalGroup(
                3, tags, name=f"{comp_id}_{mat_key}",
            )

    # ------------------------------------------------------------------ #

    def _find_bottom_surfaces(self, tol: float = 1e-6) -> list[int]:
        """Return surface tags whose bounding box has z_min and z_max near 0."""
        bottom: list[int] = []
        surfaces = gmsh.model.getEntities(dim=2)

        for _, tag in surfaces:
            xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(
                2, tag,
            )
            # A surface on the bottom face has zmin ~ 0 and zmax ~ 0
            if abs(zmin) < tol and abs(zmax) < tol:
                bottom.append(tag)

        return bottom


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


def _demo() -> None:
    """Build a sample CubeSat geometry for quick validation."""
    import sys
    import tempfile

    design = CubeSatDesign(
        mission_name="TestSat-1",
        sat_size="3U",
        subsystems=["eps", "obc", "com_uhf", "adcs"],
        payload_type="Camera (EO)",
        payload_power=5.0,
        payload_mass=200,
    )

    with tempfile.TemporaryDirectory() as tmp:
        builder = CubesatGeometryBuilder(design)
        result = builder.build(Path(tmp))

        print(f"STEP file  : {result.step_file}")
        print(f"Total vols : {result.total_volumes}")
        print(f"Structure  : {result.structure_volume_tags}")
        print(f"Bottom BC  : {result.bottom_surface_tags}")
        print(f"BBox       : {result.bounding_box}")
        print("Component volumes:")
        for cid, tags in result.component_volumes.items():
            print(f"  {cid}: {tags}")

        # Verify the file exists and has content
        step_path = Path(result.step_file)
        if step_path.exists() and step_path.stat().st_size > 0:
            size_kb = step_path.stat().st_size / 1024
            print(f"\nSUCCESS: STEP file is {size_kb:.1f} KB")
        else:
            print("\nFAILED: STEP file missing or empty", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    _demo()
