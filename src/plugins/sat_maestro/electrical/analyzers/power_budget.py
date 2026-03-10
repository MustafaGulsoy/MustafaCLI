"""Power budget analysis for satellite electrical power subsystem."""
from __future__ import annotations

import logging
from datetime import datetime

from ...core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    PinDirection,
    Severity,
    Violation,
)
from ...core.graph_ops import GraphOperations

logger = logging.getLogger(__name__)

# Default ECSS minimum power margin
DEFAULT_MIN_MARGIN = 0.20  # 20%


class PowerBudgetAnalyzer:
    """Analyze power budget and margins for satellite subsystems."""

    def __init__(self, graph: GraphOperations, derating_factor: float = 0.75) -> None:
        self._graph = graph
        self._derating_factor = derating_factor

    async def analyze(self, subsystem: str | None = None) -> AnalysisResult:
        """Run power budget analysis.

        Checks:
        1. Total power consumption vs available power
        2. Per-rail current vs source capacity (with derating)
        3. Power margin adequacy (>20% recommended by ECSS)
        """
        violations: list[Violation] = []
        rails: list[dict] = []

        # Get all components (or filter by subsystem)
        if subsystem:
            components = await self._graph.get_components_by_subsystem(subsystem)
        else:
            components = await self._graph.get_components_by_subsystem("EPS")

        # Analyze each component's power pins
        total_supply = 0.0
        total_consumption = 0.0

        for comp in components:
            pins = await self._graph.get_pins(comp.id)

            for pin in pins:
                if pin.direction != PinDirection.POWER:
                    continue

                if pin.voltage is not None and pin.current_max is not None:
                    # This is a power source or load
                    power = pin.voltage * pin.current_max

                    if pin.actual_current is not None:
                        actual_power = pin.voltage * pin.actual_current
                    else:
                        actual_power = power  # Assume worst case

                    rail_name = f"{comp.name}:{pin.name}"

                    # Check derating
                    derated_max = pin.current_max * self._derating_factor
                    actual = pin.actual_current or pin.current_max

                    if actual > derated_max:
                        violations.append(Violation(
                            rule_id="POWER-DERATING",
                            severity=Severity.ERROR,
                            message=(
                                f"{rail_name}: current {actual:.3f}A exceeds "
                                f"{self._derating_factor:.0%} derating limit "
                                f"({derated_max:.3f}A max)"
                            ),
                            component_path=f"{comp.id}/{pin.id}",
                            details={
                                "actual_current": actual,
                                "derated_max": derated_max,
                                "derating_factor": self._derating_factor,
                            },
                        ))

                    # Check margin
                    if pin.current_max > 0:
                        margin = 1.0 - (actual / pin.current_max)
                        if margin < DEFAULT_MIN_MARGIN:
                            violations.append(Violation(
                                rule_id="POWER-MARGIN",
                                severity=Severity.WARNING,
                                message=(
                                    f"{rail_name}: power margin {margin:.0%} "
                                    f"below recommended {DEFAULT_MIN_MARGIN:.0%}"
                                ),
                                component_path=f"{comp.id}/{pin.id}",
                                details={
                                    "margin": margin,
                                    "min_recommended": DEFAULT_MIN_MARGIN,
                                },
                            ))

                        rails.append({
                            "name": rail_name,
                            "voltage": pin.voltage,
                            "current_max": pin.current_max,
                            "actual_current": actual,
                            "margin": margin,
                        })

                    total_supply += pin.current_max
                    total_consumption += actual

        # Determine overall status
        has_errors = any(v.severity == Severity.ERROR for v in violations)
        has_warnings = any(v.severity == Severity.WARNING for v in violations)

        if has_errors:
            status = AnalysisStatus.FAIL
        elif has_warnings:
            status = AnalysisStatus.WARN
        else:
            status = AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="power_budget",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary={
                "total_supply_capacity": total_supply,
                "total_consumption": total_consumption,
                "overall_margin": (1.0 - total_consumption / total_supply) if total_supply > 0 else 0,
                "rails_analyzed": len(rails),
                "rails": rails,
            },
            metadata={
                "subsystem": subsystem,
                "derating_factor": self._derating_factor,
                "min_margin": DEFAULT_MIN_MARGIN,
            },
        )
