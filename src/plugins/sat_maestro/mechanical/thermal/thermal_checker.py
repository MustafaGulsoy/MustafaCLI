"""Thermal limit checker per ECSS-E-ST-31C."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ...core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)

# Default thresholds
_TEMP_WARNING_MARGIN = 5.0  # deg C from operational limits
_MAX_GRADIENT = 30.0  # deg C between connected nodes
_MIN_HEATER_MARGIN = 0.25  # 25% margin from cold limit
_MIN_RADIATOR_MARGIN = 0.20  # 20% margin from hot limit


class ThermalChecker:
    """Validates node temperatures against operational limits.

    Checks:
    - Temperature within [op_min_temp, op_max_temp] range (ERROR if out)
    - Warning if within 5 deg C of limits
    - Thermal gradient between connected nodes (max 30 deg C)
    - Heater margin >= 25%
    - Radiator margin >= 20%
    """

    def __init__(
        self,
        bridge: McpBridge,
        warning_margin: float = _TEMP_WARNING_MARGIN,
        max_gradient: float = _MAX_GRADIENT,
        min_heater_margin: float = _MIN_HEATER_MARGIN,
        min_radiator_margin: float = _MIN_RADIATOR_MARGIN,
    ) -> None:
        self._bridge = bridge
        self._warning_margin = warning_margin
        self._max_gradient = max_gradient
        self._min_heater_margin = min_heater_margin
        self._min_radiator_margin = min_radiator_margin

    async def _fetch_nodes(self) -> list[dict[str, Any]]:
        records = await self._bridge.neo4j_query(
            "MATCH (n:ThermalNode) RETURN n"
        )
        return [r["n"] for r in records]

    async def _fetch_conductances(self) -> list[dict[str, Any]]:
        records = await self._bridge.neo4j_query(
            "MATCH (c:ThermalConductance) RETURN c"
        )
        return [r["c"] for r in records]

    def _check_limits(self, node: dict[str, Any]) -> list[Violation]:
        """Check a single node against its temperature limits."""
        violations = []
        temp = node["temperature"]
        t_min = node["op_min_temp"]
        t_max = node["op_max_temp"]
        name = node["name"]
        nid = node["id"]

        # ERROR: out of operational range
        if temp > t_max:
            violations.append(Violation(
                rule_id="THERMAL-OVER-TEMP",
                severity=Severity.ERROR,
                message=f"{name}: temperature {temp:.1f} deg C exceeds max {t_max:.1f} deg C",
                component_path=nid,
                details={"temperature": temp, "op_max_temp": t_max},
            ))
        elif temp < t_min:
            violations.append(Violation(
                rule_id="THERMAL-UNDER-TEMP",
                severity=Severity.ERROR,
                message=f"{name}: temperature {temp:.1f} deg C below min {t_min:.1f} deg C",
                component_path=nid,
                details={"temperature": temp, "op_min_temp": t_min},
            ))
        else:
            # WARNING: near limits
            if temp >= t_max - self._warning_margin:
                violations.append(Violation(
                    rule_id="THERMAL-NEAR-MAX",
                    severity=Severity.WARNING,
                    message=f"{name}: temperature {temp:.1f} deg C within {self._warning_margin} deg C of max {t_max:.1f} deg C",
                    component_path=nid,
                    details={"temperature": temp, "op_max_temp": t_max, "margin": t_max - temp},
                ))
            if temp <= t_min + self._warning_margin:
                violations.append(Violation(
                    rule_id="THERMAL-NEAR-MIN",
                    severity=Severity.WARNING,
                    message=f"{name}: temperature {temp:.1f} deg C within {self._warning_margin} deg C of min {t_min:.1f} deg C",
                    component_path=nid,
                    details={"temperature": temp, "op_min_temp": t_min, "margin": temp - t_min},
                ))

        # Heater margin check (margin from cold side)
        temp_range = t_max - t_min
        if temp_range > 0:
            heater_margin = (temp - t_min) / temp_range
            if heater_margin < self._min_heater_margin and temp >= t_min:
                violations.append(Violation(
                    rule_id="THERMAL-HEATER-MARGIN",
                    severity=Severity.WARNING,
                    message=f"{name}: heater margin {heater_margin:.0%} below {self._min_heater_margin:.0%}",
                    component_path=nid,
                    details={"heater_margin": heater_margin, "min_required": self._min_heater_margin},
                ))

            # Radiator margin check (margin from hot side)
            radiator_margin = (t_max - temp) / temp_range
            if radiator_margin < self._min_radiator_margin and temp <= t_max:
                violations.append(Violation(
                    rule_id="THERMAL-RADIATOR-MARGIN",
                    severity=Severity.WARNING,
                    message=f"{name}: radiator margin {radiator_margin:.0%} below {self._min_radiator_margin:.0%}",
                    component_path=nid,
                    details={"radiator_margin": radiator_margin, "min_required": self._min_radiator_margin},
                ))

        return violations

    def _check_gradients(
        self,
        nodes: list[dict[str, Any]],
        conductances: list[dict[str, Any]],
    ) -> list[Violation]:
        """Check thermal gradients between connected nodes."""
        violations = []
        node_map = {n["id"]: n for n in nodes}

        for cond in conductances:
            a = node_map.get(cond["node_a_id"])
            b = node_map.get(cond["node_b_id"])
            if a is None or b is None:
                continue

            gradient = abs(a["temperature"] - b["temperature"])
            if gradient > self._max_gradient:
                violations.append(Violation(
                    rule_id="THERMAL-GRADIENT",
                    severity=Severity.WARNING,
                    message=(
                        f"Thermal gradient {gradient:.1f} deg C between "
                        f"{a['name']} and {b['name']} exceeds {self._max_gradient:.1f} deg C limit"
                    ),
                    component_path=f"{cond.get('id', '?')}",
                    details={
                        "node_a": a["id"],
                        "node_b": b["id"],
                        "gradient": gradient,
                        "max_gradient": self._max_gradient,
                    },
                ))

        return violations

    async def analyze(self) -> AnalysisResult:
        """Run thermal limit checks on all nodes."""
        raw_nodes = await self._fetch_nodes()
        raw_conductances = await self._fetch_conductances()

        if not raw_nodes:
            return AnalysisResult(
                analyzer="thermal_checker",
                status=AnalysisStatus.PASS,
                timestamp=datetime.now(),
                summary={"nodes_checked": 0},
            )

        violations: list[Violation] = []

        # Check each node's temperature limits
        for node in raw_nodes:
            violations.extend(self._check_limits(node))

        # Check thermal gradients
        violations.extend(self._check_gradients(raw_nodes, raw_conductances))

        # Determine status
        has_errors = any(v.severity == Severity.ERROR for v in violations)
        has_warnings = any(v.severity == Severity.WARNING for v in violations)

        if has_errors:
            status = AnalysisStatus.FAIL
        elif has_warnings:
            status = AnalysisStatus.WARN
        else:
            status = AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="thermal_checker",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary={
                "nodes_checked": len(raw_nodes),
                "errors": sum(1 for v in violations if v.severity == Severity.ERROR),
                "warnings": sum(1 for v in violations if v.severity == Severity.WARNING),
            },
        )
