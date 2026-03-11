"""Mass-Thermal correlation analyzer.

Identifies heavy components that are also hot — potential thermal management
concerns where high mass concentrations couple with high power dissipation.
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
_MASS_THRESHOLD = 5.0  # kg — flag components heavier than this
_TEMP_THRESHOLD = 60.0  # deg C — flag nodes hotter than this
_POWER_DENSITY_WARN = 50.0  # W/kg — high power-to-mass ratio

_QUERY = """
MATCH (s:Structure)-[:MOUNTS]->(c:Component)
OPTIONAL MATCH (tn:ThermalNode)-[:DISSIPATES_FROM]->(c)
RETURN s {.id, .name, .mass, .subsystem},
       c {.id, .name},
       tn {.id, .name, .temperature, .power_dissipation,
           .op_min_temp, .op_max_temp}
"""


class MassThermalAnalyzer:
    """Correlates mass budget with thermal analysis.

    Checks:
    - Heavy components (> threshold) with high temperatures
    - High power-to-mass ratio (W/kg)
    - Components without thermal nodes (missing thermal model)
    """

    def __init__(
        self,
        bridge: McpBridge,
        mass_threshold: float = _MASS_THRESHOLD,
        temp_threshold: float = _TEMP_THRESHOLD,
        power_density_warn: float = _POWER_DENSITY_WARN,
    ) -> None:
        self._bridge = bridge
        self._mass_threshold = mass_threshold
        self._temp_threshold = temp_threshold
        self._power_density_warn = power_density_warn

    async def analyze(self) -> AnalysisResult:
        records = await self._bridge.neo4j_query(_QUERY)

        if not records:
            return AnalysisResult(
                analyzer="MassThermalAnalyzer",
                status=AnalysisStatus.PASS,
                summary={"records_checked": 0},
            )

        violations: list[Violation] = []

        for rec in records:
            s = rec["s"]
            c = rec["c"]
            tn = rec.get("tn")
            mass = s.get("mass", 0.0)
            comp_name = c.get("name", c["id"])
            struct_name = s.get("name", s["id"])

            # Missing thermal node for mounted component
            if tn is None:
                violations.append(Violation(
                    rule_id="CROSS-MT-001",
                    severity=Severity.WARNING,
                    message=f"Component '{comp_name}' on '{struct_name}' has no thermal node",
                    component_path=f"/cross/mass_thermal/{c['id']}",
                    details={"component_id": c["id"], "structure_id": s["id"]},
                ))
                continue

            temp = tn.get("temperature", 0.0)
            power = tn.get("power_dissipation", 0.0)

            # Heavy + hot
            if mass >= self._mass_threshold and temp >= self._temp_threshold:
                violations.append(Violation(
                    rule_id="CROSS-MT-002",
                    severity=Severity.WARNING,
                    message=(f"Heavy+hot: '{comp_name}' mass={mass:.1f} kg, "
                             f"temp={temp:.1f} deg C"),
                    component_path=f"/cross/mass_thermal/{c['id']}",
                    details={"mass": mass, "temperature": temp,
                             "component_id": c["id"], "structure_id": s["id"]},
                ))

            # High power density
            if mass > 0 and power / mass > self._power_density_warn:
                density = power / mass
                violations.append(Violation(
                    rule_id="CROSS-MT-003",
                    severity=Severity.WARNING,
                    message=(f"High power density: '{comp_name}' "
                             f"{density:.1f} W/kg (power={power:.1f} W, mass={mass:.1f} kg)"),
                    component_path=f"/cross/mass_thermal/{c['id']}",
                    details={"power_density": density, "power": power, "mass": mass},
                ))

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        status = AnalysisStatus.FAIL if has_errors else (
            AnalysisStatus.WARN if violations else AnalysisStatus.PASS
        )

        return AnalysisResult(
            analyzer="MassThermalAnalyzer",
            status=status,
            violations=violations,
            summary={
                "records_checked": len(records),
                "errors": sum(1 for v in violations if v.severity == Severity.ERROR),
                "warnings": sum(1 for v in violations if v.severity == Severity.WARNING),
            },
        )
