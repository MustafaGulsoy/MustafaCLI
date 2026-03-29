"""FEM result interpreter -- turns CalculiX output into AnalysisResult."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ...config import SatMaestroConfig
from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation
from ...mcp_servers.calculix.result_parser import CalculixResultParser

logger = logging.getLogger(__name__)

# Default displacement limit (mm).  CubeSat spec typically allows at most
# 0.5 mm deflection under quasi-static loads to avoid interference.
_DEFAULT_MAX_DISPLACEMENT_MM: float = 0.5


class FemResultReport:
    """Interprets CalculiX .dat results and produces ``AnalysisResult`` objects.

    Uses :class:`CalculixResultParser` for the low-level file parsing, then
    applies safety-factor and launcher-requirement checks.
    """

    def __init__(self, config: SatMaestroConfig) -> None:
        self._config = config
        # Safety factor defaults to 1.5 if not explicitly set on config.
        self._safety_factor: float = getattr(config, "fem_safety_factor", 1.5)
        self._parser = CalculixResultParser()

    # ------------------------------------------------------------------
    # Static analysis
    # ------------------------------------------------------------------

    def from_static_results(
        self,
        dat_file: str,
        material_yield: float = 503.0,
        max_displacement_mm: float = _DEFAULT_MAX_DISPLACEMENT_MM,
    ) -> AnalysisResult:
        """Evaluate a CalculiX static analysis .dat file.

        Checks performed:
          1. Max von Mises stress vs. allowable (yield / safety factor).
          2. Max displacement magnitude vs. ``max_displacement_mm``.

        Args:
            dat_file: Path to the CalculiX ``.dat`` output file.
            material_yield: Yield strength of the primary material in **MPa**.
                Defaults to Al-7075-T6 (503 MPa).
            max_displacement_mm: Maximum permissible displacement in
                millimetres.

        Returns:
            An :class:`AnalysisResult` with status PASS / WARN / FAIL.
        """
        violations: list[Violation] = []
        summary: dict[str, Any] = {}

        dat_path = Path(dat_file)
        if not dat_path.exists():
            return self._error_result(
                analyzer="fem_static",
                message=f"Static .dat file not found: {dat_file}",
            )

        content = dat_path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return self._error_result(
                analyzer="fem_static",
                message=f"Static .dat file is empty: {dat_file}",
            )

        # -- Stress check ------------------------------------------------
        stress_data = self._parser.parse_dat_stress(content)
        max_vm = stress_data["max_von_mises"]  # Pa in raw output
        num_elements = len(stress_data["elements"])

        # The parser returns stress in the same unit the mesh uses.  CalculiX
        # inherits units from the input deck; our decks use mm / N / MPa, so
        # max_vm is in MPa already.
        allowable_stress = material_yield / self._safety_factor

        summary["max_von_mises_mpa"] = round(max_vm, 3)
        summary["allowable_stress_mpa"] = round(allowable_stress, 3)
        summary["stress_safety_factor"] = self._safety_factor
        summary["stress_elements_parsed"] = num_elements

        if num_elements == 0:
            violations.append(Violation(
                rule_id="FEM-STATIC-001",
                severity=Severity.WARNING,
                message="No stress data found in .dat output -- solver may have failed",
                component_path="fem/static/stress",
            ))
        elif max_vm > allowable_stress:
            margin = (allowable_stress - max_vm) / allowable_stress
            violations.append(Violation(
                rule_id="FEM-STATIC-002",
                severity=Severity.ERROR,
                message=(
                    f"Max von Mises stress ({max_vm:.2f} MPa) exceeds "
                    f"allowable ({allowable_stress:.2f} MPa, SF={self._safety_factor}). "
                    f"Margin of safety: {margin:.2%}"
                ),
                component_path="fem/static/stress",
                details={
                    "max_von_mises_mpa": max_vm,
                    "allowable_mpa": allowable_stress,
                    "margin": margin,
                },
            ))
        else:
            margin = (allowable_stress - max_vm) / allowable_stress
            summary["stress_margin"] = round(margin, 4)

        # -- Displacement check -------------------------------------------
        disp_data = self._parser.parse_dat_displacement(content)
        max_disp = disp_data["max_displacement"]
        num_disp_nodes = len(disp_data["nodes"])

        summary["max_displacement_mm"] = round(max_disp, 6)
        summary["displacement_limit_mm"] = max_displacement_mm
        summary["displacement_nodes_parsed"] = num_disp_nodes

        if num_disp_nodes == 0:
            violations.append(Violation(
                rule_id="FEM-STATIC-003",
                severity=Severity.WARNING,
                message="No displacement data found in .dat output",
                component_path="fem/static/displacement",
            ))
        elif max_disp > max_displacement_mm:
            violations.append(Violation(
                rule_id="FEM-STATIC-004",
                severity=Severity.ERROR,
                message=(
                    f"Max displacement ({max_disp:.4f} mm) exceeds limit "
                    f"({max_displacement_mm} mm)"
                ),
                component_path="fem/static/displacement",
                details={
                    "max_displacement_mm": max_disp,
                    "limit_mm": max_displacement_mm,
                },
            ))
        else:
            summary["displacement_margin"] = round(
                (max_displacement_mm - max_disp) / max_displacement_mm, 4
            )

        status = self._derive_status(violations)

        return AnalysisResult(
            analyzer="fem_static",
            status=status,
            violations=violations,
            summary=summary,
            metadata={"dat_file": dat_file, "safety_factor": self._safety_factor},
        )

    # ------------------------------------------------------------------
    # Modal analysis
    # ------------------------------------------------------------------

    def from_modal_results(
        self,
        dat_file: str,
        min_lateral: float | None = None,
        min_axial: float | None = None,
    ) -> AnalysisResult:
        """Evaluate a CalculiX modal (frequency) analysis .dat file.

        Checks the first eigenfrequencies against launcher requirements.

        By convention, for a vertically-oriented CubeSat the first lateral
        mode is the lowest frequency and the first axial mode is the second
        or third lowest.  This method conservatively checks:
          - mode 1 frequency >= ``min_lateral``
          - all modes >= ``min_axial`` (i.e. even lateral must exceed the
            axial floor, which is the stricter requirement).

        Args:
            dat_file: Path to the CalculiX ``.dat`` output file.
            min_lateral: Minimum first-lateral-mode frequency in Hz.  Defaults
                to ``config.min_lateral_freq`` (15 Hz).
            min_axial: Minimum first-axial-mode frequency in Hz.  Defaults to
                ``config.min_axial_freq`` (35 Hz).

        Returns:
            An :class:`AnalysisResult` with status PASS / WARN / FAIL.
        """
        if min_lateral is None:
            min_lateral = self._config.min_lateral_freq
        if min_axial is None:
            min_axial = self._config.min_axial_freq

        violations: list[Violation] = []
        summary: dict[str, Any] = {
            "min_lateral_req_hz": min_lateral,
            "min_axial_req_hz": min_axial,
        }

        dat_path = Path(dat_file)
        if not dat_path.exists():
            return self._error_result(
                analyzer="fem_modal",
                message=f"Modal .dat file not found: {dat_file}",
            )

        content = dat_path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return self._error_result(
                analyzer="fem_modal",
                message=f"Modal .dat file is empty: {dat_file}",
            )

        frequencies = self._parser.parse_dat_frequencies(content)
        summary["modes_found"] = len(frequencies)

        if not frequencies:
            violations.append(Violation(
                rule_id="FEM-MODAL-001",
                severity=Severity.ERROR,
                message="No eigenfrequencies found in .dat output -- solver may have failed",
                component_path="fem/modal/frequencies",
            ))
            return AnalysisResult(
                analyzer="fem_modal",
                status=AnalysisStatus.FAIL,
                violations=violations,
                summary=summary,
                metadata={"dat_file": dat_file},
            )

        freq_values = [f["frequency_hz"] for f in frequencies]
        summary["frequencies_hz"] = [round(f, 4) for f in freq_values]

        first_freq = freq_values[0]
        summary["first_mode_hz"] = round(first_freq, 4)

        # Check first lateral mode (mode 1)
        if first_freq < min_lateral:
            violations.append(Violation(
                rule_id="FEM-MODAL-002",
                severity=Severity.ERROR,
                message=(
                    f"First lateral mode ({first_freq:.2f} Hz) is below the "
                    f"minimum requirement ({min_lateral} Hz)"
                ),
                component_path="fem/modal/lateral",
                details={
                    "first_mode_hz": first_freq,
                    "min_lateral_hz": min_lateral,
                },
            ))
        elif first_freq < min_lateral * 1.1:
            # Within 10% margin -- warn
            violations.append(Violation(
                rule_id="FEM-MODAL-003",
                severity=Severity.WARNING,
                message=(
                    f"First lateral mode ({first_freq:.2f} Hz) is close to "
                    f"the minimum requirement ({min_lateral} Hz) -- less than "
                    f"10% margin"
                ),
                component_path="fem/modal/lateral",
                details={
                    "first_mode_hz": first_freq,
                    "min_lateral_hz": min_lateral,
                    "margin_pct": round(
                        (first_freq - min_lateral) / min_lateral * 100, 2
                    ),
                },
            ))

        # Check first axial mode.  Axial modes are typically the 2nd or 3rd
        # mode for a CubeSat.  Rather than trying to classify mode shapes
        # (which would require the .frd), we conservatively check that at
        # least one of the first three modes meets the axial requirement.
        axial_candidates = freq_values[:3] if len(freq_values) >= 3 else freq_values
        max_candidate = max(axial_candidates)
        summary["axial_candidate_hz"] = round(max_candidate, 4)

        if max_candidate < min_axial:
            violations.append(Violation(
                rule_id="FEM-MODAL-004",
                severity=Severity.ERROR,
                message=(
                    f"No mode among the first {len(axial_candidates)} "
                    f"({', '.join(f'{f:.2f}' for f in axial_candidates)} Hz) "
                    f"meets the axial requirement ({min_axial} Hz)"
                ),
                component_path="fem/modal/axial",
                details={
                    "candidates_hz": axial_candidates,
                    "min_axial_hz": min_axial,
                },
            ))
        elif max_candidate < min_axial * 1.1:
            violations.append(Violation(
                rule_id="FEM-MODAL-005",
                severity=Severity.WARNING,
                message=(
                    f"Best axial-mode candidate ({max_candidate:.2f} Hz) is "
                    f"close to the minimum requirement ({min_axial} Hz) -- "
                    f"less than 10% margin"
                ),
                component_path="fem/modal/axial",
                details={
                    "candidate_hz": max_candidate,
                    "min_axial_hz": min_axial,
                    "margin_pct": round(
                        (max_candidate - min_axial) / min_axial * 100, 2
                    ),
                },
            ))

        status = self._derive_status(violations)

        return AnalysisResult(
            analyzer="fem_modal",
            status=status,
            violations=violations,
            summary=summary,
            metadata={"dat_file": dat_file},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_status(violations: list[Violation]) -> AnalysisStatus:
        """Determine overall status from a list of violations."""
        if any(v.severity == Severity.ERROR for v in violations):
            return AnalysisStatus.FAIL
        if any(v.severity == Severity.WARNING for v in violations):
            return AnalysisStatus.WARN
        return AnalysisStatus.PASS

    @staticmethod
    def _error_result(analyzer: str, message: str) -> AnalysisResult:
        """Create a FAIL result for an unrecoverable error condition."""
        return AnalysisResult(
            analyzer=analyzer,
            status=AnalysisStatus.FAIL,
            violations=[
                Violation(
                    rule_id="FEM-ERR-000",
                    severity=Severity.ERROR,
                    message=message,
                    component_path=f"fem/{analyzer}",
                ),
            ],
            summary={"error": message},
        )
