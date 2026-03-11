"""Gmsh Python API wrapper for mesh generation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import gmsh
except ImportError:
    gmsh = None


class GmshMesher:
    """Wrapper around Gmsh Python API for mesh generation and manipulation."""

    def mesh_from_step(self, step_file: str, element_size: float = 5.0,
                       element_type: str = "tet", order: int = 2) -> dict[str, Any]:
        """Generate FEM mesh from STEP file."""
        if gmsh is None:
            raise ImportError("gmsh package required. Install with: pip install gmsh")

        gmsh.initialize()
        try:
            gmsh.open(step_file)
            gmsh.option.setNumber("Mesh.MeshSizeMax", element_size)
            gmsh.option.setNumber("Mesh.MeshSizeMin", element_size * 0.1)
            gmsh.option.setNumber("Mesh.ElementOrder", order)

            if element_type == "hex":
                gmsh.option.setNumber("Mesh.Algorithm3D", 9)  # hex-dominant
            else:
                gmsh.option.setNumber("Mesh.Algorithm3D", 1)  # Delaunay tet

            gmsh.model.mesh.generate(3)

            out_path = str(Path(step_file).with_suffix(".msh"))
            gmsh.write(out_path)

            nodes, _, _ = gmsh.model.mesh.getNodes()
            elem_types, _, _ = gmsh.model.mesh.getElements()

            return {
                "mesh_file": out_path,
                "node_count": len(nodes),
                "element_types": len(elem_types),
                "element_size": element_size,
                "order": order,
            }
        finally:
            gmsh.finalize()

    def mesh_from_geo(self, geo_file: str, element_size: float = 5.0) -> dict[str, Any]:
        """Generate mesh from .geo script."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(geo_file)
            gmsh.option.setNumber("Mesh.MeshSizeMax", element_size)
            gmsh.model.mesh.generate(3)

            out_path = str(Path(geo_file).with_suffix(".msh"))
            gmsh.write(out_path)

            nodes, _, _ = gmsh.model.mesh.getNodes()
            return {"mesh_file": out_path, "node_count": len(nodes)}
        finally:
            gmsh.finalize()

    def quality_check(self, mesh_file: str, metric: str = "gamma") -> dict[str, Any]:
        """Check mesh quality."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(mesh_file)
            qualities = gmsh.model.mesh.getElementQualities(qualityType=metric)
            return {
                "min_quality": min(qualities) if qualities else 0.0,
                "max_quality": max(qualities) if qualities else 0.0,
                "avg_quality": sum(qualities) / len(qualities) if qualities else 0.0,
                "elements_below_03": sum(1 for q in qualities if q < 0.3),
                "total_elements": len(qualities),
            }
        finally:
            gmsh.finalize()

    def info(self, mesh_file: str) -> dict[str, Any]:
        """Get mesh statistics."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(mesh_file)
            nodes, _, _ = gmsh.model.mesh.getNodes()
            elem_types, elem_tags, _ = gmsh.model.mesh.getElements()
            total_elems = sum(len(t) for t in elem_tags)
            return {
                "node_count": len(nodes),
                "element_count": total_elems,
                "element_types": len(elem_types),
            }
        finally:
            gmsh.finalize()

    def convert(self, mesh_file: str, output_format: str = "inp") -> str:
        """Convert mesh to different format."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(mesh_file)
            out_path = str(Path(mesh_file).with_suffix(f".{output_format}"))
            gmsh.write(out_path)
            return out_path
        finally:
            gmsh.finalize()

    def refine_region(self, mesh_file: str, box: dict, target_size: float) -> str:
        """Refine mesh in a box region."""
        if gmsh is None:
            raise ImportError("gmsh package required")

        gmsh.initialize()
        try:
            gmsh.open(mesh_file)
            field = gmsh.model.mesh.field.add("Box")
            gmsh.model.mesh.field.setNumber(field, "VIn", target_size)
            gmsh.model.mesh.field.setNumber(field, "VOut", target_size * 5)
            gmsh.model.mesh.field.setNumber(field, "XMin", box.get("x_min", 0))
            gmsh.model.mesh.field.setNumber(field, "XMax", box.get("x_max", 1))
            gmsh.model.mesh.field.setNumber(field, "YMin", box.get("y_min", 0))
            gmsh.model.mesh.field.setNumber(field, "YMax", box.get("y_max", 1))
            gmsh.model.mesh.field.setNumber(field, "ZMin", box.get("z_min", 0))
            gmsh.model.mesh.field.setNumber(field, "ZMax", box.get("z_max", 1))
            gmsh.model.mesh.field.setAsBackgroundMesh(field)
            gmsh.model.mesh.generate(3)

            out_path = str(Path(mesh_file).with_suffix(".refined.msh"))
            gmsh.write(out_path)
            return out_path
        finally:
            gmsh.finalize()
