"""Random vibration analysis (PSD to gRMS, Miles' equation)."""
from __future__ import annotations

import logging
import math
from typing import Any, TYPE_CHECKING

from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation

if TYPE_CHECKING:
    from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)


class RandomVibAnalyzer:
    """Random vibration analysis: PSD integration and Miles' equation."""

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    async def analyze(
        self,
        psd_profile: list[dict[str, float]],
        grms_limit: float | None = None,
    ) -> AnalysisResult:
        """Compute gRMS from PSD profile and check against limits.

        Args:
            psd_profile: List of dicts with freq_hz and psd_g2hz.
            grms_limit: Maximum allowed gRMS level.
        """
        violations: list[Violation] = []

        if not psd_profile:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-VIB-000",
                severity=Severity.WARNING,
                message="No PSD profile data provided",
                component_path="spacecraft",
            ))
            return AnalysisResult(
                analyzer="random_vibration",
                status=AnalysisStatus.WARN,
                violations=violations,
                summary={"grms": 0.0, "freq_range": None},
            )

        sorted_psd = sorted(psd_profile, key=lambda p: p["freq_hz"])
        grms = self._compute_grms(sorted_psd)
        freq_range = (sorted_psd[0]["freq_hz"], sorted_psd[-1]["freq_hz"])

        if grms_limit is not None and grms > grms_limit:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-VIB-001",
                severity=Severity.ERROR,
                message=f"gRMS {grms:.2f} g exceeds limit {grms_limit:.2f} g",
                component_path="spacecraft",
                details={"grms": grms, "limit": grms_limit},
            ))

        status = AnalysisStatus.FAIL if any(v.severity == Severity.ERROR for v in violations) \
            else AnalysisStatus.WARN if violations else AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="random_vibration",
            status=status,
            violations=violations,
            summary={
                "grms": grms,
                "freq_range": freq_range,
            },
        )

    @staticmethod
    def _compute_grms(sorted_psd: list[dict[str, float]]) -> float:
        """Integrate PSD using trapezoidal rule to get gRMS."""
        area = 0.0
        for i in range(len(sorted_psd) - 1):
            f1 = sorted_psd[i]["freq_hz"]
            f2 = sorted_psd[i + 1]["freq_hz"]
            p1 = sorted_psd[i]["psd_g2hz"]
            p2 = sorted_psd[i + 1]["psd_g2hz"]
            area += 0.5 * (p1 + p2) * (f2 - f1)
        return math.sqrt(area)

    @staticmethod
    def miles_response(fn: float, q: float, psd_level: float) -> float:
        """Miles' equation for SDOF response to random vibration.

        Args:
            fn: Natural frequency (Hz).
            q: Quality factor (amplification).
            psd_level: PSD level at fn (g^2/Hz).

        Returns:
            gRMS response.
        """
        return math.sqrt(math.pi / 2 * fn * q * psd_level)
