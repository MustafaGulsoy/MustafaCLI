"""Modal analysis evaluation against ECSS frequency requirements."""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation

if TYPE_CHECKING:
    from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)


class ModalAnalyzer:
    """Evaluates CalculiX modal analysis results against ECSS frequency limits.

    ECSS-E-ST-32C requirements:
    - First lateral frequency >= 15 Hz (launcher-dependent)
    - First axial frequency >= 35 Hz
    """

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    async def evaluate(
        self,
        modes: list[dict[str, Any]],
        min_lateral_hz: float = 15.0,
        min_axial_hz: float = 35.0,
    ) -> AnalysisResult:
        """Evaluate modal frequencies against ECSS limits.

        Args:
            modes: List of mode dicts with keys: mode, frequency_hz, eigenvalue.
            min_lateral_hz: Minimum first lateral frequency (Hz).
            min_axial_hz: Minimum first axial frequency (Hz).
        """
        violations: list[Violation] = []

        if not modes:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-MODAL-000",
                severity=Severity.WARNING,
                message="No modal analysis results provided",
                component_path="spacecraft",
            ))
            return AnalysisResult(
                analyzer="modal_analysis",
                status=AnalysisStatus.WARN,
                violations=violations,
                summary={"mode_count": 0, "first_frequency_hz": None},
            )

        sorted_modes = sorted(modes, key=lambda m: m["frequency_hz"])
        first_freq = sorted_modes[0]["frequency_hz"]

        # Check first frequency against lateral limit
        if first_freq < min_lateral_hz:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-MODAL-001",
                severity=Severity.ERROR,
                message=f"First lateral frequency {first_freq:.1f} Hz below limit {min_lateral_hz:.1f} Hz",
                component_path="spacecraft",
                details={"frequency_hz": first_freq, "limit_hz": min_lateral_hz},
            ))

        # Check first frequency against axial limit
        if first_freq < min_axial_hz:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-MODAL-002",
                severity=Severity.ERROR,
                message=f"First axial frequency {first_freq:.1f} Hz below limit {min_axial_hz:.1f} Hz",
                component_path="spacecraft",
                details={"frequency_hz": first_freq, "limit_hz": min_axial_hz},
            ))

        status = AnalysisStatus.FAIL if any(v.severity == Severity.ERROR for v in violations) \
            else AnalysisStatus.WARN if violations else AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="modal_analysis",
            status=status,
            violations=violations,
            summary={
                "mode_count": len(sorted_modes),
                "first_frequency_hz": first_freq,
                "modes": [{"mode": m["mode"], "frequency_hz": m["frequency_hz"]} for m in sorted_modes],
                "min_lateral_hz": min_lateral_hz,
                "min_axial_hz": min_axial_hz,
            },
        )
