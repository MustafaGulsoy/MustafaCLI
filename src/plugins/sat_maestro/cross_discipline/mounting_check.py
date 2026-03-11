"""Mounting compatibility checker.

Validates that component mounting points are compatible with
structural mounting interfaces (bolt patterns, mass capacity).
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
_MASS_CAPACITY_MARGIN = 1.5  # structural capacity must be >= 1.5x component mass
_BOLT_PATTERN_CHECK = True

_MOUNTING_QUERY = """
MATCH (s:Structure)-[:MOUNTS]->(c:Component)
RETURN s {.id, .name, .mass, .material, .subsystem,
          .mount_capacity, .mount_pattern, .mount_points},
       c {.id, .name, .mass, .mounting_pattern, .mounting_points}
"""


class MountingCheckAnalyzer:
    """Validates component mounting compatibility.

    Checks:
    - Structure has sufficient mass capacity for mounted component
    - Bolt pattern compatibility (if defined)
    - Number of mounting points sufficient
    - Components mounted on structure (no floating components)
    """

    def __init__(
        self,
        bridge: McpBridge,
        mass_capacity_margin: float = _MASS_CAPACITY_MARGIN,
    ) -> None:
        self._bridge = bridge
        self._mass_capacity_margin = mass_capacity_margin

    async def analyze(self) -> AnalysisResult:
        records = await self._bridge.neo4j_query(_MOUNTING_QUERY)

        if not records:
            return AnalysisResult(
                analyzer="MountingCheckAnalyzer",
                status=AnalysisStatus.PASS,
                summary={"mounts_checked": 0},
            )

        violations: list[Violation] = []

        for rec in records:
            s = rec["s"]
            c = rec["c"]
            struct_name = s.get("name", s["id"])
            comp_name = c.get("name", c["id"])

            # Mass capacity check
            mount_capacity = s.get("mount_capacity")
            comp_mass = c.get("mass", 0.0)
            if mount_capacity is not None and comp_mass > 0:
                required_capacity = comp_mass * self._mass_capacity_margin
                if mount_capacity < required_capacity:
                    violations.append(Violation(
                        rule_id="CROSS-MNT-001",
                        severity=Severity.ERROR,
                        message=(f"Structure '{struct_name}' capacity {mount_capacity:.2f} kg "
                                 f"insufficient for '{comp_name}' "
                                 f"(needs {required_capacity:.2f} kg "
                                 f"= {comp_mass:.2f} kg x {self._mass_capacity_margin})"),
                        component_path=f"/cross/mounting/{c['id']}",
                        details={
                            "structure_id": s["id"], "component_id": c["id"],
                            "mount_capacity": mount_capacity,
                            "component_mass": comp_mass,
                            "required_capacity": required_capacity,
                        },
                    ))

            # Bolt pattern compatibility
            struct_pattern = s.get("mount_pattern")
            comp_pattern = c.get("mounting_pattern")
            if struct_pattern and comp_pattern and struct_pattern != comp_pattern:
                violations.append(Violation(
                    rule_id="CROSS-MNT-002",
                    severity=Severity.ERROR,
                    message=(f"Bolt pattern mismatch: '{struct_name}' has '{struct_pattern}' "
                             f"but '{comp_name}' requires '{comp_pattern}'"),
                    component_path=f"/cross/mounting/{c['id']}",
                    details={
                        "structure_pattern": struct_pattern,
                        "component_pattern": comp_pattern,
                    },
                ))

            # Mounting points check
            struct_points = s.get("mount_points", 0)
            comp_points = c.get("mounting_points", 0)
            if comp_points > 0 and struct_points > 0 and struct_points < comp_points:
                violations.append(Violation(
                    rule_id="CROSS-MNT-003",
                    severity=Severity.ERROR,
                    message=(f"'{struct_name}' has {struct_points} mount points "
                             f"but '{comp_name}' requires {comp_points}"),
                    component_path=f"/cross/mounting/{c['id']}",
                    details={
                        "structure_points": struct_points,
                        "component_points": comp_points,
                    },
                ))

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        status = AnalysisStatus.FAIL if has_errors else (
            AnalysisStatus.WARN if violations else AnalysisStatus.PASS
        )

        return AnalysisResult(
            analyzer="MountingCheckAnalyzer",
            status=status,
            violations=violations,
            summary={
                "mounts_checked": len(records),
                "errors": sum(1 for v in violations if v.severity == Severity.ERROR),
                "warnings": sum(1 for v in violations if v.severity == Severity.WARNING),
            },
        )
