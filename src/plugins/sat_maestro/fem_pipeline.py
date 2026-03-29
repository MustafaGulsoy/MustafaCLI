"""End-to-end FEM pipeline orchestrator for CubeSat structural analysis.

Orchestrates the full pipeline: geometry build -> mesh generation -> CalculiX
solve -> result interpretation. Each step is fault-tolerant; partial results
are returned when a downstream step fails.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import SatMaestroConfig
from .core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation
from .cubesat_wizard import CubeSatDesign

logger = logging.getLogger(__name__)


@dataclass
class FemPipelineResult:
    """Aggregated result from the full FEM pipeline."""

    step_file: str = ""
    mesh_inp_file: str = ""
    calculix_inp_file: str = ""
    dat_file: str | None = None
    node_count: int = 0
    element_count: int = 0
    max_stress_mpa: float | None = None
    max_displacement_mm: float | None = None
    first_frequency_hz: float | None = None
    analysis_result: AnalysisResult = field(
        default_factory=lambda: AnalysisResult(
            analyzer="fem_pipeline",
            status=AnalysisStatus.WARN,
            summary={"info": "Pipeline did not complete"},
        )
    )


class FemPipeline:
    """Orchestrates geometry -> mesh -> solve -> report for a CubeSat design.

    The pipeline is designed to be resilient: if CalculiX is unavailable or
    fails, the user still receives the STEP model and mesh files together
    with a WARN-level analysis result instead of a hard failure.
    """

    def __init__(self, config: SatMaestroConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, design: CubeSatDesign) -> FemPipelineResult:
        """Execute the full FEM pipeline for *design*.

        Args:
            design: A fully populated CubeSat design from the wizard.

        Returns:
            FemPipelineResult with as many fields populated as the pipeline
            managed to produce before encountering an error (if any).
        """
        result = FemPipelineResult()
        violations: list[Violation] = []

        output_dir = (
            Path(self._config.report_output_dir) / design.mission_name / "fem"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        # ---- Step 1: Build 3D geometry (STEP) --------------------------
        try:
            logger.info("FEM Step 1/5: Building 3D geometry ...")
            from .mechanical.structural.geometry_builder import CubesatGeometryBuilder

            builder = CubesatGeometryBuilder(design)
            geometry = builder.build(output_dir)
            result.step_file = str(geometry.step_file) if hasattr(geometry, "step_file") else str(geometry)
            logger.info("  STEP file: %s", result.step_file)
        except Exception as exc:
            msg = f"Geometry build failed: {exc}"
            logger.error(msg)
            violations.append(
                Violation(
                    rule_id="FEM-GEO-001",
                    severity=Severity.ERROR,
                    message=msg,
                    component_path="fem_pipeline.geometry_builder",
                )
            )
            result.analysis_result = self._build_analysis(
                AnalysisStatus.FAIL, violations, result
            )
            return result

        # ---- Step 2: Generate mesh -------------------------------------
        try:
            logger.info("FEM Step 2/5: Generating mesh ...")
            from .mcp_servers.gmsh.mesher import GmshMesher

            mesher = GmshMesher()
            element_size = self._config.fem_element_size
            mesh_info = mesher.mesh_from_step(
                result.step_file, element_size=element_size
            )
            result.node_count = mesh_info.get("node_count", 0)

            # Convert .msh -> .inp for CalculiX
            mesh_msh = mesh_info["mesh_file"]
            inp_path = mesher.convert(mesh_msh, output_format="inp")
            result.mesh_inp_file = inp_path

            # Retrieve element count from mesh info
            info = mesher.info(mesh_msh)
            result.element_count = info.get("element_count", 0)
            logger.info(
                "  Mesh: %d nodes, %d elements", result.node_count, result.element_count
            )
        except ImportError as exc:
            msg = f"Gmsh not available: {exc}"
            logger.warning(msg)
            violations.append(
                Violation(
                    rule_id="FEM-MESH-001",
                    severity=Severity.WARNING,
                    message=msg,
                    component_path="fem_pipeline.mesher",
                )
            )
            result.analysis_result = self._build_analysis(
                AnalysisStatus.WARN, violations, result
            )
            return result
        except Exception as exc:
            msg = f"Mesh generation failed: {exc}"
            logger.error(msg)
            violations.append(
                Violation(
                    rule_id="FEM-MESH-002",
                    severity=Severity.ERROR,
                    message=msg,
                    component_path="fem_pipeline.mesher",
                )
            )
            result.analysis_result = self._build_analysis(
                AnalysisStatus.WARN, violations, result
            )
            return result

        # ---- Step 3: Write CalculiX input deck -------------------------
        try:
            logger.info("FEM Step 3/5: Writing CalculiX input deck ...")
            from .mechanical.structural.calculix_writer import CalculixInputWriter

            writer = CalculixInputWriter(
                mesh_inp_path=result.mesh_inp_file,
                component_elsets=getattr(result, '_physical_groups', {}),
            )
            ccx_input = writer.write_static_analysis(output_dir)
            result.calculix_inp_file = str(
                ccx_input.inp_file if hasattr(ccx_input, "inp_file") else ccx_input
            )
            logger.info("  CalculiX input: %s", result.calculix_inp_file)
        except Exception as exc:
            msg = f"CalculiX input generation failed: {exc}"
            logger.error(msg)
            violations.append(
                Violation(
                    rule_id="FEM-CCX-001",
                    severity=Severity.ERROR,
                    message=msg,
                    component_path="fem_pipeline.calculix_writer",
                )
            )
            result.analysis_result = self._build_analysis(
                AnalysisStatus.WARN, violations, result
            )
            return result

        # ---- Step 4: Run CalculiX solver -------------------------------
        solve_result: dict[str, Any] = {}
        try:
            logger.info("FEM Step 4/5: Running CalculiX solver ...")
            from .mcp_servers.calculix.solver import CalculixSolver

            solver = CalculixSolver(self._config.calculix_path)
            solve_result = await solver.solve(result.calculix_inp_file)
            result.dat_file = solve_result.get("dat_file")
            logger.info("  Solver completed. dat_file=%s", result.dat_file)
        except FileNotFoundError as exc:
            msg = f"CalculiX executable not found: {exc}"
            logger.warning(msg)
            violations.append(
                Violation(
                    rule_id="FEM-SOLVE-001",
                    severity=Severity.WARNING,
                    message=msg,
                    component_path="fem_pipeline.solver",
                    details={"calculix_path": self._config.calculix_path},
                )
            )
            result.analysis_result = self._build_analysis(
                AnalysisStatus.WARN, violations, result
            )
            return result
        except RuntimeError as exc:
            msg = f"CalculiX solver failed: {exc}"
            logger.error(msg)
            violations.append(
                Violation(
                    rule_id="FEM-SOLVE-002",
                    severity=Severity.ERROR,
                    message=msg,
                    component_path="fem_pipeline.solver",
                )
            )
            result.analysis_result = self._build_analysis(
                AnalysisStatus.WARN, violations, result
            )
            return result

        # ---- Step 5: Interpret results ---------------------------------
        try:
            logger.info("FEM Step 5/5: Interpreting results ...")
            result.max_stress_mpa = solve_result.get("max_von_mises")
            result.max_displacement_mm = (
                solve_result["max_displacement"] * 1000.0
                if solve_result.get("max_displacement") is not None
                else None
            )

            frequencies = solve_result.get("frequencies", [])
            if frequencies:
                result.first_frequency_hz = frequencies[0]

            # Structural margin check (ECSS safety factor)
            self._check_structural_margins(design, result, violations)

            # Frequency check
            self._check_frequency_requirements(result, violations)

            status = (
                AnalysisStatus.FAIL
                if any(v.severity == Severity.ERROR for v in violations)
                else AnalysisStatus.WARN
                if violations
                else AnalysisStatus.PASS
            )
            result.analysis_result = self._build_analysis(status, violations, result)

        except Exception as exc:
            msg = f"Result interpretation failed: {exc}"
            logger.error(msg)
            violations.append(
                Violation(
                    rule_id="FEM-REPORT-001",
                    severity=Severity.WARNING,
                    message=msg,
                    component_path="fem_pipeline.fem_report",
                )
            )
            result.analysis_result = self._build_analysis(
                AnalysisStatus.WARN, violations, result
            )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_structural_margins(
        self,
        design: CubeSatDesign,
        result: FemPipelineResult,
        violations: list[Violation],
    ) -> None:
        """Compare max stress against Al-7075 yield with ECSS safety factor."""
        if result.max_stress_mpa is None:
            return

        # Al-7075-T6 yield strength: 503 MPa
        al7075_yield_mpa = 503.0
        safety_factor = self._config.fem_safety_factor
        allowable_mpa = al7075_yield_mpa / safety_factor

        if result.max_stress_mpa > allowable_mpa:
            violations.append(
                Violation(
                    rule_id="FEM-MARGIN-001",
                    severity=Severity.ERROR,
                    message=(
                        f"Max stress {result.max_stress_mpa:.1f} MPa exceeds "
                        f"allowable {allowable_mpa:.1f} MPa "
                        f"(Al-7075 yield={al7075_yield_mpa:.0f} MPa, "
                        f"SF={safety_factor})"
                    ),
                    component_path=f"{design.mission_name}.structure",
                    details={
                        "max_stress_mpa": result.max_stress_mpa,
                        "allowable_mpa": allowable_mpa,
                        "yield_mpa": al7075_yield_mpa,
                        "safety_factor": safety_factor,
                    },
                )
            )
        else:
            margin = (allowable_mpa / result.max_stress_mpa) - 1.0
            logger.info(
                "  Structural margin of safety: %.2f (min required: 0.0)", margin
            )

    def _check_frequency_requirements(
        self,
        result: FemPipelineResult,
        violations: list[Violation],
    ) -> None:
        """Verify first natural frequency against launcher requirements."""
        if result.first_frequency_hz is None:
            return

        min_lateral = self._config.min_lateral_freq
        if result.first_frequency_hz < min_lateral:
            violations.append(
                Violation(
                    rule_id="FEM-FREQ-001",
                    severity=Severity.ERROR,
                    message=(
                        f"First natural frequency {result.first_frequency_hz:.1f} Hz "
                        f"is below minimum lateral requirement {min_lateral:.1f} Hz"
                    ),
                    component_path="fem_pipeline.frequency_check",
                    details={
                        "first_freq_hz": result.first_frequency_hz,
                        "min_lateral_hz": min_lateral,
                    },
                )
            )

    def _build_analysis(
        self,
        status: AnalysisStatus,
        violations: list[Violation],
        result: FemPipelineResult,
    ) -> AnalysisResult:
        """Construct an AnalysisResult summarising the pipeline outcome."""
        summary: dict[str, Any] = {
            "step_file": result.step_file,
            "mesh_inp_file": result.mesh_inp_file,
            "calculix_inp_file": result.calculix_inp_file,
            "node_count": result.node_count,
            "element_count": result.element_count,
        }
        if result.max_stress_mpa is not None:
            summary["max_stress_mpa"] = result.max_stress_mpa
        if result.max_displacement_mm is not None:
            summary["max_displacement_mm"] = result.max_displacement_mm
        if result.first_frequency_hz is not None:
            summary["first_frequency_hz"] = result.first_frequency_hz

        return AnalysisResult(
            analyzer="fem_pipeline",
            status=status,
            violations=list(violations),
            summary=summary,
            metadata={
                "calculix_path": self._config.calculix_path,
                "element_size_mm": self._config.fem_element_size,
                "wall_thickness_mm": self._config.fem_wall_thickness,
                "safety_factor": self._config.fem_safety_factor,
            },
        )
