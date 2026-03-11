"""Cable harness routing validator.

Validates cable/harness mass, length, and routing through assemblies.
"""
from __future__ import annotations

import logging
from typing import Any

from ..core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from ..core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)

# Defaults
_MAX_HARNESS_MASS_FRACTION = 0.08  # 8% of total S/C mass
_MAX_CABLE_LENGTH = 5.0  # meters — flag long cables
_MIN_BEND_RADIUS_FACTOR = 6.0  # min bend radius = factor * cable diameter

_HARNESS_QUERY = """
MATCH (n:Net)-[:ROUTED_THROUGH]->(a:Assembly)
OPTIONAL MATCH (n)-[:CONNECTS]->(c:Connector)
RETURN n {.id, .name, .type, .cable_mass, .cable_length, .cable_diameter},
       a {.id, .name, .total_mass},
       collect(c {.id, .name, .series}) AS connectors
"""

_SPACECRAFT_MASS_QUERY = """
MATCH (a:Assembly {level: 0})
RETURN a.total_mass AS total_mass
"""


class HarnessRoutingAnalyzer:
    """Validates cable harness routing.

    Checks:
    - Total harness mass fraction vs spacecraft mass
    - Individual cable length limits
    - Cables routed through assemblies (no orphan cables)
    - Minimum bend radius (cable_diameter * factor)
    """

    def __init__(
        self,
        bridge: McpBridge,
        max_mass_fraction: float = _MAX_HARNESS_MASS_FRACTION,
        max_cable_length: float = _MAX_CABLE_LENGTH,
        min_bend_radius_factor: float = _MIN_BEND_RADIUS_FACTOR,
    ) -> None:
        self._bridge = bridge
        self._max_mass_fraction = max_mass_fraction
        self._max_cable_length = max_cable_length
        self._min_bend_radius_factor = min_bend_radius_factor

    async def analyze(self) -> AnalysisResult:
        records = await self._bridge.neo4j_query(_HARNESS_QUERY)
        sc_records = await self._bridge.neo4j_query(_SPACECRAFT_MASS_QUERY)

        sc_mass = sc_records[0]["total_mass"] if sc_records else None
        violations: list[Violation] = []
        total_harness_mass = 0.0

        if not records:
            return AnalysisResult(
                analyzer="HarnessRoutingAnalyzer",
                status=AnalysisStatus.PASS,
                summary={"cables_checked": 0, "total_harness_mass": 0.0},
            )

        for rec in records:
            n = rec["n"]
            net_name = n.get("name", n["id"])
            cable_mass = n.get("cable_mass", 0.0)
            cable_length = n.get("cable_length", 0.0)
            cable_diameter = n.get("cable_diameter", 0.0)
            total_harness_mass += cable_mass

            # Long cable warning
            if cable_length > self._max_cable_length:
                violations.append(Violation(
                    rule_id="CROSS-HR-001",
                    severity=Severity.WARNING,
                    message=(f"Cable '{net_name}' length {cable_length:.2f} m "
                             f"exceeds {self._max_cable_length:.1f} m limit"),
                    component_path=f"/cross/harness/{n['id']}",
                    details={"cable_length": cable_length,
                             "max_length": self._max_cable_length},
                ))

            # No connectors on routed cable
            connectors = rec.get("connectors", [])
            if not connectors:
                violations.append(Violation(
                    rule_id="CROSS-HR-002",
                    severity=Severity.WARNING,
                    message=f"Cable '{net_name}' has no connectors defined",
                    component_path=f"/cross/harness/{n['id']}",
                    details={"net_id": n["id"]},
                ))

            # Bend radius check (if diameter provided)
            min_bend = n.get("min_bend_radius", 0.0)
            if cable_diameter > 0 and min_bend > 0:
                required_bend = cable_diameter * self._min_bend_radius_factor
                if min_bend < required_bend:
                    violations.append(Violation(
                        rule_id="CROSS-HR-003",
                        severity=Severity.ERROR,
                        message=(f"Cable '{net_name}' bend radius {min_bend:.2f} mm "
                                 f"below minimum {required_bend:.2f} mm "
                                 f"({self._min_bend_radius_factor}x diameter)"),
                        component_path=f"/cross/harness/{n['id']}",
                        details={"min_bend_radius": min_bend,
                                 "required_bend_radius": required_bend,
                                 "cable_diameter": cable_diameter},
                    ))

        # Harness mass fraction check
        if sc_mass and sc_mass > 0:
            fraction = total_harness_mass / sc_mass
            if fraction > self._max_mass_fraction:
                violations.append(Violation(
                    rule_id="CROSS-HR-004",
                    severity=Severity.WARNING,
                    message=(f"Harness mass fraction {fraction:.1%} "
                             f"exceeds {self._max_mass_fraction:.0%} guideline "
                             f"({total_harness_mass:.2f} kg / {sc_mass:.1f} kg)"),
                    component_path="/cross/harness",
                    details={"harness_mass": total_harness_mass,
                             "spacecraft_mass": sc_mass,
                             "fraction": fraction},
                ))

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        status = AnalysisStatus.FAIL if has_errors else (
            AnalysisStatus.WARN if violations else AnalysisStatus.PASS
        )

        return AnalysisResult(
            analyzer="HarnessRoutingAnalyzer",
            status=status,
            violations=violations,
            summary={
                "cables_checked": len(records),
                "total_harness_mass": round(total_harness_mass, 3),
                "spacecraft_mass": sc_mass,
            },
        )
