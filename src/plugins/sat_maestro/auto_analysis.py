"""Auto-analysis runner -- executes all analyzers after bus generation.

Runs mass budget, power budget, pin voltage check, thermal steady-state,
and thermal limit checks in sequence.  Each analyzer is wrapped in
try/except so that a single failure does not crash the pipeline.
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime
from typing import TYPE_CHECKING

from .core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from .cubesat_wizard import CubeSatDesign
from .mechanical.structural.mass_budget import MassBudgetAnalyzer
from .mechanical.thermal.node_model import ThermalNodeModel
from .mechanical.thermal.thermal_checker import ThermalChecker

if TYPE_CHECKING:
    from .config import SatMaestroConfig
    from .core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)

# LEO average sunlit fraction (~60 % of orbit period)
_LEO_SUNLIT_FRACTION: float = 0.60

# Voltage tolerance for pin-to-pin connection checks (5 %)
_VOLTAGE_TOLERANCE: float = 0.05


def _status_symbol(status: AnalysisStatus) -> str:
    """Return a plain-text symbol for the given status."""
    return {
        AnalysisStatus.PASS: "PASS",
        AnalysisStatus.WARN: "WARN",
        AnalysisStatus.FAIL: "FAIL",
    }[status]


def _safe_result(analyzer_name: str, error: Exception) -> AnalysisResult:
    """Create a WARN result when an analyzer raises unexpectedly."""
    return AnalysisResult(
        analyzer=analyzer_name,
        status=AnalysisStatus.WARN,
        timestamp=datetime.now(),
        violations=[
            Violation(
                rule_id=f"{analyzer_name.upper()}-RUNTIME",
                severity=Severity.WARNING,
                message=f"Analyzer could not run: {error}",
                component_path="auto_analysis",
                details={"traceback": traceback.format_exc()},
            )
        ],
        summary={"skipped": True, "reason": str(error)},
    )


class AutoAnalysisRunner:
    """Orchestrates the full analysis suite against a CubeSat design.

    Each check is executed inside a try/except guard so that missing
    Neo4j data or unavailable services degrade gracefully into a WARN
    result rather than aborting the entire pipeline.
    """

    def __init__(self, bridge: McpBridge, config: SatMaestroConfig) -> None:
        self._bridge = bridge
        self._config = config

    # ------------------------------------------------------------------
    # Individual analysis steps
    # ------------------------------------------------------------------

    async def _run_mass_budget(self, design: CubeSatDesign) -> AnalysisResult:
        """Step 1 -- Mass budget against size-class limit."""
        analyzer = MassBudgetAnalyzer(
            self._bridge,
            mass_margin=self._config.mass_margin,
        )
        budget_kg: float = design.limits["max_mass_kg"]
        return await analyzer.analyze(budget=budget_kg)

    async def _run_power_budget(self, design: CubeSatDesign) -> AnalysisResult:
        """Step 2 -- Simple power budget from Component nodes.

        Sums positive ``power_w`` values as consumers and treats
        negative ``power_w`` (solar panels) as generation.  Generation
        is derated by the LEO sunlit fraction to obtain orbit-average
        available power.
        """
        violations: list[Violation] = []

        records = await self._bridge.neo4j_query(
            "MATCH (c:Component) "
            "RETURN c.id AS id, c.name AS name, "
            "       c.power_w AS power_w, c.subsystem AS subsystem"
        )

        total_consumption: float = 0.0
        total_generation: float = 0.0

        for rec in records:
            power = rec.get("power_w") or 0.0
            if power > 0:
                total_consumption += power
            elif power < 0:
                total_generation += abs(power)

        # Orbit-average generation (sunlit fraction)
        avg_generation = total_generation * _LEO_SUNLIT_FRACTION

        # Also consider the size-class orbit-average limit
        orbit_avg_limit = design.limits.get("max_power_orbit_avg_w", 0.0)

        margin = (
            (avg_generation - total_consumption) / avg_generation
            if avg_generation > 0
            else -1.0
        )

        if total_consumption > avg_generation:
            violations.append(
                Violation(
                    rule_id="POWER-BUDGET-001",
                    severity=Severity.WARNING,
                    message=(
                        f"Power consumption {total_consumption:.1f} W exceeds "
                        f"orbit-avg generation {avg_generation:.1f} W "
                        f"(solar {total_generation:.1f} W x {_LEO_SUNLIT_FRACTION:.0%} sunlit)"
                    ),
                    component_path="spacecraft/power",
                    details={
                        "consumption_w": total_consumption,
                        "generation_w": total_generation,
                        "avg_generation_w": avg_generation,
                        "sunlit_fraction": _LEO_SUNLIT_FRACTION,
                    },
                )
            )

        if total_consumption > orbit_avg_limit > 0:
            violations.append(
                Violation(
                    rule_id="POWER-BUDGET-002",
                    severity=Severity.WARNING,
                    message=(
                        f"Total consumption {total_consumption:.1f} W exceeds "
                        f"{design.sat_size} orbit-avg limit {orbit_avg_limit:.1f} W"
                    ),
                    component_path="spacecraft/power",
                    details={
                        "consumption_w": total_consumption,
                        "orbit_avg_limit_w": orbit_avg_limit,
                    },
                )
            )

        has_error = any(v.severity == Severity.ERROR for v in violations)
        has_warning = any(v.severity == Severity.WARNING for v in violations)
        status = (
            AnalysisStatus.FAIL
            if has_error
            else AnalysisStatus.WARN
            if has_warning
            else AnalysisStatus.PASS
        )

        return AnalysisResult(
            analyzer="power_budget",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary={
                "total_consumption_w": total_consumption,
                "total_generation_w": total_generation,
                "avg_generation_w": avg_generation,
                "sunlit_fraction": _LEO_SUNLIT_FRACTION,
                "orbit_avg_limit_w": orbit_avg_limit,
                "margin": margin,
                "component_count": len(records),
            },
        )

    async def _run_pin_voltage_check(self) -> AnalysisResult:
        """Step 3 -- Verify connected pins have compatible voltages.

        Queries all ``CONNECTED_TO`` relationships between Pin nodes and
        checks that the voltages on each end are within the tolerance.
        """
        violations: list[Violation] = []

        records = await self._bridge.neo4j_query(
            "MATCH (a:Pin)-[r:CONNECTED_TO]->(b:Pin) "
            "RETURN a.id AS src_id, a.name AS src_name, a.voltage AS src_v, "
            "       b.id AS dst_id, b.name AS dst_name, b.voltage AS dst_v"
        )

        total_connections = len(records)
        ok_connections = 0

        for rec in records:
            src_v = rec.get("src_v")
            dst_v = rec.get("dst_v")

            # Skip pins without voltage information
            if src_v is None or dst_v is None:
                ok_connections += 1
                continue

            src_v = float(src_v)
            dst_v = float(dst_v)

            # Zero-voltage pins (passive / antenna) are always OK
            if src_v == 0.0 or dst_v == 0.0:
                ok_connections += 1
                continue

            max_v = max(abs(src_v), abs(dst_v))
            diff = abs(src_v - dst_v)
            threshold = max_v * _VOLTAGE_TOLERANCE

            if diff > threshold:
                violations.append(
                    Violation(
                        rule_id="PIN-VOLTAGE-001",
                        severity=Severity.ERROR,
                        message=(
                            f"Voltage mismatch: {rec.get('src_name', rec['src_id'])} "
                            f"({src_v:.2f} V) -> "
                            f"{rec.get('dst_name', rec['dst_id'])} "
                            f"({dst_v:.2f} V), diff {diff:.2f} V "
                            f"exceeds {_VOLTAGE_TOLERANCE:.0%} tolerance"
                        ),
                        component_path=f"{rec['src_id']}->{rec['dst_id']}",
                        details={
                            "src_voltage": src_v,
                            "dst_voltage": dst_v,
                            "diff": diff,
                            "tolerance": _VOLTAGE_TOLERANCE,
                        },
                    )
                )
            else:
                ok_connections += 1

        has_error = any(v.severity == Severity.ERROR for v in violations)
        status = (
            AnalysisStatus.FAIL
            if has_error
            else AnalysisStatus.PASS
        )

        return AnalysisResult(
            analyzer="pin_voltage_check",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary={
                "total_connections": total_connections,
                "ok_connections": ok_connections,
                "mismatches": len(violations),
            },
        )

    async def _run_thermal_steady_state(self) -> AnalysisResult:
        """Step 4 -- Solve lumped-parameter thermal model if nodes exist."""
        solver = ThermalNodeModel(self._bridge)
        return await solver.analyze()

    async def _run_thermal_limits(self) -> AnalysisResult:
        """Step 5 -- Verify node temperatures are within operational range."""
        checker = ThermalChecker(self._bridge)
        return await checker.analyze()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_all(self, design: CubeSatDesign) -> list[AnalysisResult]:
        """Run the complete analysis suite.

        Each analyzer is wrapped in a try/except so that failures in one
        step do not prevent the remaining analyses from executing.

        Args:
            design: The CubeSat design produced by the wizard.

        Returns:
            A list of ``AnalysisResult`` objects, one per analysis step.
        """
        steps: list[tuple[str, object]] = [
            ("mass_budget", lambda: self._run_mass_budget(design)),
            ("power_budget", lambda: self._run_power_budget(design)),
            ("pin_voltage_check", lambda: self._run_pin_voltage_check()),
            ("thermal_node_model", lambda: self._run_thermal_steady_state()),
            ("thermal_checker", lambda: self._run_thermal_limits()),
        ]

        results: list[AnalysisResult] = []

        for name, step_fn in steps:
            try:
                logger.info("Running analysis: %s", name)
                result = await step_fn()
                results.append(result)
                logger.info(
                    "Analysis %s completed: %s", name, result.status.value
                )
            except Exception as exc:
                logger.warning(
                    "Analysis %s failed with %s: %s",
                    name,
                    type(exc).__name__,
                    exc,
                )
                results.append(_safe_result(name, exc))

        return results

    # ------------------------------------------------------------------
    # Report formatting
    # ------------------------------------------------------------------

    def format_report(
        self,
        design: CubeSatDesign,
        results: list[AnalysisResult],
    ) -> str:
        """Generate a readable CLI report from analysis results.

        Args:
            design: The CubeSat design for header information.
            results: List of analysis results from ``run_all``.

        Returns:
            A formatted ASCII table string suitable for terminal output.
        """
        # Compute box width based on content
        inner_width = 56

        # Build the detail line for each result
        detail_lines: list[tuple[str, str, str]] = []
        for r in results:
            label = _friendly_name(r.analyzer)
            status_str = _status_symbol(r.status)
            detail = _summary_detail(r)
            detail_lines.append((label, status_str, detail))

        # Ensure the box is wide enough for all content
        for label, status_str, detail in detail_lines:
            needed = len(label) + len(status_str) + len(detail) + 6  # padding
            inner_width = max(inner_width, needed)

        # Also ensure the title fits
        title = f"{design.mission_name} -- Analysis Report"
        inner_width = max(inner_width, len(title) + 4)

        # Count violations
        total_warnings = sum(
            1
            for r in results
            for v in r.violations
            if v.severity == Severity.WARNING
        )
        total_errors = sum(
            1
            for r in results
            for v in r.violations
            if v.severity == Severity.ERROR
        )

        lines: list[str] = []

        # Top border
        lines.append(f"+{'=' * (inner_width + 2)}+")

        # Title
        lines.append(f"| {title:^{inner_width}} |")

        # Separator
        lines.append(f"+{'-' * (inner_width + 2)}+")

        # Result rows
        for label, status_str, detail in detail_lines:
            left = f"{label:<22}{status_str:<7}{detail}"
            lines.append(f"| {left:<{inner_width}} |")

        # Separator before violations summary
        lines.append(f"+{'-' * (inner_width + 2)}+")

        # Violation summary
        violation_text = (
            f"Violations: {total_warnings} WARNING, {total_errors} ERROR"
        )
        lines.append(f"| {violation_text:<{inner_width}} |")

        # List individual violations if any
        all_violations = [v for r in results for v in r.violations]
        if all_violations:
            lines.append(f"|{' ' * (inner_width + 2)}|")
            for v in all_violations:
                prefix = f"  [{v.severity.value}]"
                msg = v.message
                max_msg_len = inner_width - len(prefix) - 1
                if len(msg) > max_msg_len:
                    msg = msg[: max_msg_len - 3] + "..."
                vline = f"{prefix} {msg}"
                lines.append(f"| {vline:<{inner_width}} |")

        # Bottom border
        lines.append(f"+{'=' * (inner_width + 2)}+")

        return "\n".join(lines)


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _friendly_name(analyzer_id: str) -> str:
    """Map analyzer identifier to a human-friendly label."""
    names: dict[str, str] = {
        "mass_budget": "Mass Budget",
        "power_budget": "Power Budget",
        "pin_voltage_check": "Pin Voltage Check",
        "thermal_node_model": "Thermal Analysis",
        "thermal_checker": "Thermal Limits",
    }
    return names.get(analyzer_id, analyzer_id)


def _summary_detail(result: AnalysisResult) -> str:
    """Build a short detail string from the result summary dict."""
    s = result.summary
    analyzer = result.analyzer

    if s.get("skipped"):
        return f"(skipped: {s.get('reason', 'unknown')[:30]})"

    if analyzer == "mass_budget":
        total = s.get("total_mass", 0.0)
        budget = s.get("budget", 0.0)
        pct = (total / budget * 100) if budget > 0 else 0.0
        return f"{total:.2f}kg / {budget:.1f}kg  ({pct:.1f}%)"

    if analyzer == "power_budget":
        consumption = s.get("total_consumption_w", 0.0)
        avg_gen = s.get("avg_generation_w", 0.0)
        return f"{consumption:.1f}W / {avg_gen:.1f}W avg"

    if analyzer == "pin_voltage_check":
        total = s.get("total_connections", 0)
        ok = s.get("ok_connections", 0)
        return f"{ok}/{total} connections OK"

    if analyzer == "thermal_node_model":
        temps = s.get("temperatures", {})
        if not temps:
            count = s.get("node_count", 0)
            return f"{count} nodes (no data)" if count == 0 else "solved"
        t_min = s.get("min_temp", 0.0)
        t_max = s.get("max_temp", 0.0)
        return f"{t_min:.0f}C to {t_max:.0f}C range"

    if analyzer == "thermal_checker":
        checked = s.get("nodes_checked", 0)
        errors = s.get("errors", 0)
        warnings = s.get("warnings", 0)
        if errors == 0 and warnings == 0:
            return f"All {checked} nodes within op range"
        return f"{checked} nodes, {errors} errors, {warnings} warnings"

    # Fallback for unknown analyzers
    return str(s)[:40]
