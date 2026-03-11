"""Mass budget analysis for satellite structures."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation

if TYPE_CHECKING:
    from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)


class MassBudgetAnalyzer:
    """Analyzes spacecraft mass budget against allocation with ECSS margins."""

    def __init__(self, bridge: McpBridge, mass_margin: float = 0.10) -> None:
        self._bridge = bridge
        self._margin_threshold = mass_margin

    async def analyze(self, budget: float, subsystem: str | None = None) -> AnalysisResult:
        """Run mass budget analysis.

        Args:
            budget: Total mass budget in kg.
            subsystem: Optional subsystem filter.
        """
        violations: list[Violation] = []

        query = "MATCH (a:Assembly) RETURN a.name AS name, a.total_mass AS total_mass"
        if subsystem:
            query = f"MATCH (a:Assembly {{name: '{subsystem}'}}) RETURN a.name AS name, a.total_mass AS total_mass"

        records = await self._bridge.neo4j_query(query)

        subsystems = []
        total_mass = 0.0
        for r in records:
            mass = r.get("total_mass", 0.0) or 0.0
            total_mass += mass
            subsystems.append({"name": r["name"], "mass": mass})

        margin = (budget - total_mass) / budget if budget > 0 else 1.0

        if total_mass > budget:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-MASS-001",
                severity=Severity.ERROR,
                message=f"Total mass {total_mass:.1f} kg exceeds budget {budget:.1f} kg",
                component_path="spacecraft",
                details={"total_mass": total_mass, "budget": budget},
            ))
        elif margin < self._margin_threshold:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-MASS-002",
                severity=Severity.WARNING,
                message=f"Mass margin {margin:.1%} below threshold {self._margin_threshold:.0%}",
                component_path="spacecraft",
                details={"margin": margin, "threshold": self._margin_threshold},
            ))

        status = AnalysisStatus.FAIL if any(v.severity == Severity.ERROR for v in violations) \
            else AnalysisStatus.WARN if violations else AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="mass_budget",
            status=status,
            violations=violations,
            summary={
                "total_mass": total_mass,
                "budget": budget,
                "margin": margin,
                "subsystems": subsystems,
            },
        )
