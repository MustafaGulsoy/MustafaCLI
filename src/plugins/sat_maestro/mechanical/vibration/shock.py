"""Shock analysis - SRS comparison against qualification levels."""
from __future__ import annotations

import logging
import math
from typing import Any, TYPE_CHECKING

from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation

if TYPE_CHECKING:
    from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)


class ShockAnalyzer:
    """Shock Response Spectrum (SRS) analysis against qualification levels."""

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    async def evaluate(
        self,
        srs_data: list[dict[str, float]],
        qual_levels: list[dict[str, float]],
        margin_db: float = 3.0,
    ) -> AnalysisResult:
        """Compare SRS data against qualification levels with margin.

        Args:
            srs_data: List of dicts with freq_hz and accel_g.
            qual_levels: Qualification SRS levels (freq_hz, accel_g).
            margin_db: Safety margin in dB (default 3 dB).
        """
        violations: list[Violation] = []

        if not srs_data or not qual_levels:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-SHOCK-000",
                severity=Severity.WARNING,
                message="No SRS data or qualification levels provided",
                component_path="spacecraft",
            ))
            return AnalysisResult(
                analyzer="shock_analysis",
                status=AnalysisStatus.WARN,
                violations=violations,
                summary={"max_ratio": 0.0, "points_checked": 0},
            )

        margin_factor = 10 ** (margin_db / 20.0)
        qual_dict = {q["freq_hz"]: q["accel_g"] for q in qual_levels}
        max_ratio = 0.0
        points_checked = 0

        for point in srs_data:
            freq = point["freq_hz"]
            accel = point["accel_g"]

            qual_accel = self._interpolate_qual(freq, qual_levels)
            if qual_accel is None:
                continue

            effective_limit = qual_accel / margin_factor
            ratio = accel / effective_limit if effective_limit > 0 else float("inf")
            max_ratio = max(max_ratio, ratio)
            points_checked += 1

            if accel > qual_accel:
                violations.append(Violation(
                    rule_id="ECSS-E-ST-32C-SHOCK-001",
                    severity=Severity.ERROR,
                    message=f"SRS at {freq:.0f} Hz: {accel:.1f} g exceeds qualification {qual_accel:.1f} g",
                    component_path="spacecraft",
                    details={"freq_hz": freq, "accel_g": accel, "qual_g": qual_accel},
                ))

        status = AnalysisStatus.FAIL if any(v.severity == Severity.ERROR for v in violations) \
            else AnalysisStatus.WARN if violations else AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="shock_analysis",
            status=status,
            violations=violations,
            summary={
                "max_ratio": max_ratio,
                "points_checked": points_checked,
                "margin_db": margin_db,
            },
        )

    @staticmethod
    def _interpolate_qual(freq: float, qual_levels: list[dict[str, float]]) -> float | None:
        """Interpolate qualification level at given frequency (log-log)."""
        sorted_quals = sorted(qual_levels, key=lambda q: q["freq_hz"])

        if freq <= sorted_quals[0]["freq_hz"]:
            return sorted_quals[0]["accel_g"]
        if freq >= sorted_quals[-1]["freq_hz"]:
            return sorted_quals[-1]["accel_g"]

        for i in range(len(sorted_quals) - 1):
            f1, a1 = sorted_quals[i]["freq_hz"], sorted_quals[i]["accel_g"]
            f2, a2 = sorted_quals[i + 1]["freq_hz"], sorted_quals[i + 1]["accel_g"]
            if f1 <= freq <= f2:
                log_ratio = math.log10(freq / f1) / math.log10(f2 / f1)
                return a1 * (a2 / a1) ** log_ratio

        return None
