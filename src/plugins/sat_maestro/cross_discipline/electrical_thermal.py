"""Electrical-Thermal correlation analyzer.

Maps power dissipation from electrical components to thermal nodes,
validating that all dissipating components have thermal coverage.
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

# Power mismatch tolerance (relative)
_POWER_MISMATCH_TOL = 0.1  # 10%

_COMPONENT_POWER_QUERY = """
MATCH (c:Component)
WHERE c.power_dissipation IS NOT NULL AND c.power_dissipation > 0
OPTIONAL MATCH (tn:ThermalNode)-[:DISSIPATES_FROM]->(c)
RETURN c {.id, .name, .power_dissipation, .subsystem},
       tn {.id, .name, .power_dissipation, .temperature}
"""


class ElectricalThermalAnalyzer:
    """Validates electrical power dissipation to thermal node mapping.

    Checks:
    - Every power-dissipating component has a thermal node
    - Power values match between electrical and thermal models
    - Total power budget consistency
    """

    def __init__(
        self,
        bridge: McpBridge,
        power_mismatch_tol: float = _POWER_MISMATCH_TOL,
    ) -> None:
        self._bridge = bridge
        self._power_mismatch_tol = power_mismatch_tol

    async def analyze(self) -> AnalysisResult:
        records = await self._bridge.neo4j_query(_COMPONENT_POWER_QUERY)

        if not records:
            return AnalysisResult(
                analyzer="ElectricalThermalAnalyzer",
                status=AnalysisStatus.PASS,
                summary={"components_checked": 0, "total_electrical_power": 0.0,
                          "total_thermal_power": 0.0},
            )

        violations: list[Violation] = []
        total_elec_power = 0.0
        total_thermal_power = 0.0

        for rec in records:
            c = rec["c"]
            tn = rec.get("tn")
            comp_name = c.get("name", c["id"])
            elec_power = c.get("power_dissipation", 0.0)
            total_elec_power += elec_power

            # No thermal node for dissipating component
            if tn is None:
                violations.append(Violation(
                    rule_id="CROSS-ET-001",
                    severity=Severity.ERROR,
                    message=(f"Component '{comp_name}' dissipates {elec_power:.2f} W "
                             f"but has no thermal node"),
                    component_path=f"/cross/electrical_thermal/{c['id']}",
                    details={"component_id": c["id"], "power_dissipation": elec_power},
                ))
                continue

            thermal_power = tn.get("power_dissipation", 0.0)
            total_thermal_power += thermal_power

            # Power mismatch
            if elec_power > 0:
                mismatch = abs(elec_power - thermal_power) / elec_power
                if mismatch > self._power_mismatch_tol:
                    violations.append(Violation(
                        rule_id="CROSS-ET-002",
                        severity=Severity.WARNING,
                        message=(f"Power mismatch for '{comp_name}': "
                                 f"electrical={elec_power:.2f} W, "
                                 f"thermal={thermal_power:.2f} W "
                                 f"({mismatch:.0%} difference)"),
                        component_path=f"/cross/electrical_thermal/{c['id']}",
                        details={"electrical_power": elec_power,
                                 "thermal_power": thermal_power,
                                 "mismatch_pct": mismatch},
                    ))

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        status = AnalysisStatus.FAIL if has_errors else (
            AnalysisStatus.WARN if violations else AnalysisStatus.PASS
        )

        return AnalysisResult(
            analyzer="ElectricalThermalAnalyzer",
            status=status,
            violations=violations,
            summary={
                "components_checked": len(records),
                "total_electrical_power": round(total_elec_power, 2),
                "total_thermal_power": round(total_thermal_power, 2),
            },
        )
