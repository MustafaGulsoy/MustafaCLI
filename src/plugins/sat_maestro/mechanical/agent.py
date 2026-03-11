"""MechanicalAgent - orchestrates all mechanical engineering analyses."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation
from .structural.mass_budget import MassBudgetAnalyzer
from .structural.cog_calculator import CogCalculator
from .structural.assembly_validator import AssemblyValidator
from .thermal.node_model import ThermalNodeModel
from .thermal.thermal_checker import ThermalChecker
from .thermal.orbital_cycle import OrbitalCycleAnalyzer
from .mechanism.deployment import DeploymentValidator
from .mechanism.kinematic import KinematicAnalyzer
from .vibration.modal import ModalAnalyzer
from .vibration.random_vib import RandomVibAnalyzer
from .vibration.shock import ShockAnalyzer

if TYPE_CHECKING:
    from ..core.mcp_bridge import McpBridge
    from ..config import SatMaestroConfig

logger = logging.getLogger(__name__)


class MechanicalAgent:
    """Orchestrates all mechanical analyses."""

    def __init__(self, bridge: McpBridge, config: SatMaestroConfig) -> None:
        self.mass_budget = MassBudgetAnalyzer(bridge, config.mass_margin)
        self.cog = CogCalculator(bridge)
        self.assembly = AssemblyValidator(bridge)
        self.thermal_solver = ThermalNodeModel(bridge)
        self.thermal_checker = ThermalChecker(bridge)
        self.orbital_cycle = OrbitalCycleAnalyzer(bridge)
        self.deployment = DeploymentValidator(bridge)
        self.kinematic = KinematicAnalyzer(bridge)
        self.modal = ModalAnalyzer(bridge)
        self.random_vib = RandomVibAnalyzer(bridge)
        self.shock = ShockAnalyzer(bridge)
        self._config = config

    async def run_full_analysis(
        self,
        mass_budget: float = 100.0,
        max_cog_offset: float | None = None,
    ) -> tuple[list[AnalysisResult], str]:
        """Run all mechanical analyses and return results with summary.

        Args:
            mass_budget: Total mass budget in kg.
            max_cog_offset: Optional CoG offset limit in meters.

        Returns:
            Tuple of (list of AnalysisResult, overall summary string).
        """
        analyses = [
            ("mass_budget", lambda: self.mass_budget.analyze(budget=mass_budget)),
            ("cog", lambda: self.cog.calculate(max_offset=max_cog_offset)),
            ("assembly", lambda: self.assembly.validate()),
            ("thermal_solver", lambda: self.thermal_solver.analyze()),
            ("thermal_checker", lambda: self.thermal_checker.analyze()),
            ("orbital_cycle", lambda: self.orbital_cycle.analyze()),
            ("deployment", lambda: self.deployment.validate()),
            ("kinematic", lambda: self.kinematic.analyze()),
        ]

        results: list[AnalysisResult] = []
        for name, run_fn in analyses:
            try:
                result = await run_fn()
                results.append(result)
            except Exception as e:
                logger.error("Analyzer '%s' failed: %s", name, e)
                results.append(AnalysisResult(
                    analyzer=name,
                    status=AnalysisStatus.FAIL,
                    violations=[Violation(
                        rule_id="INTERNAL-ERROR",
                        severity=Severity.ERROR,
                        message=f"Analyzer '{name}' raised: {e}",
                        component_path="mechanical_agent",
                    )],
                ))

        return results, self._build_summary(results)

    async def run_structural(
        self,
        mass_budget: float = 100.0,
        max_cog_offset: float | None = None,
    ) -> tuple[list[AnalysisResult], str]:
        """Run only structural analyses (mass, CoG, assembly)."""
        results: list[AnalysisResult] = []

        results.append(await self.mass_budget.analyze(budget=mass_budget))
        results.append(await self.cog.calculate(max_offset=max_cog_offset))
        results.append(await self.assembly.validate())

        return results, self._build_summary(results)

    @staticmethod
    def _build_summary(results: list[AnalysisResult]) -> str:
        """Build a human-readable summary from analysis results."""
        total = len(results)
        passed = sum(1 for r in results if r.status == AnalysisStatus.PASS)
        warned = sum(1 for r in results if r.status == AnalysisStatus.WARN)
        failed = sum(1 for r in results if r.status == AnalysisStatus.FAIL)

        all_violations = [v for r in results for v in r.violations]
        errors = sum(1 for v in all_violations if v.severity == Severity.ERROR)
        warnings = sum(1 for v in all_violations if v.severity == Severity.WARNING)

        if failed > 0:
            overall = "FAIL"
        elif warned > 0:
            overall = "WARN"
        else:
            overall = "PASS"

        lines = [
            f"Mechanical Analysis: {overall}",
            f"  Analyzers: {total} total, {passed} passed, {warned} warned, {failed} failed",
            f"  Violations: {errors} errors, {warnings} warnings",
        ]

        if failed > 0:
            lines.append("  Failed:")
            for r in results:
                if r.status == AnalysisStatus.FAIL:
                    lines.append(f"    - {r.analyzer}")

        return "\n".join(lines)
