"""Assembly tree validation for satellite structures."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation

if TYPE_CHECKING:
    from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)


class AssemblyValidator:
    """Validates assembly hierarchy consistency."""

    def __init__(self, bridge: McpBridge, mass_tolerance: float = 0.01) -> None:
        self._bridge = bridge
        self._mass_tolerance = mass_tolerance

    async def validate(self) -> AnalysisResult:
        """Run all assembly tree validation checks."""
        violations: list[Violation] = []

        # 1. Check for cycles in CONTAINS hierarchy
        cycle_records = await self._bridge.neo4j_query(
            "MATCH p=(a:Assembly)-[:CONTAINS*]->(a) RETURN p AS path LIMIT 10"
        )
        for r in cycle_records:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-ASM-001",
                severity=Severity.ERROR,
                message=f"Cycle detected in assembly hierarchy: {r.get('path', 'unknown')}",
                component_path="assembly_tree",
            ))

        # 2. Check for orphan structures (not belonging to any assembly)
        orphan_records = await self._bridge.neo4j_query(
            "MATCH (s:Structure) WHERE NOT ()-[:CONTAINS]->(s) RETURN s.name AS name"
        )
        for r in orphan_records:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-ASM-002",
                severity=Severity.WARNING,
                message=f"Orphan structure '{r['name']}' not assigned to any assembly",
                component_path=f"structure/{r['name']}",
            ))

        # 3. Check for missing material references
        missing_mat_records = await self._bridge.neo4j_query(
            "MATCH (s:Structure) WHERE s.material IS NOT NULL "
            "AND NOT EXISTS { MATCH (m:Material {name: s.material}) } "
            "RETURN s.name AS struct_name, s.material AS material"
        )
        for r in missing_mat_records:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-ASM-003",
                severity=Severity.ERROR,
                message=f"Material '{r['material']}' referenced by structure "
                        f"'{r['struct_name']}' not found in graph",
                component_path=f"structure/{r['struct_name']}",
                details={"material": r["material"]},
            ))

        # 4. Check mass roll-up consistency
        mass_records = await self._bridge.neo4j_query(
            "MATCH (a:Assembly)-[:CONTAINS]->(child) "
            "WITH a, sum(COALESCE(child.total_mass, child.mass, 0)) AS child_sum "
            "WHERE a.total_mass IS NOT NULL "
            "AND abs(a.total_mass - child_sum) > a.total_mass * $tolerance "
            "RETURN a.name AS name, a.total_mass AS total_mass, child_sum AS child_sum",
            {"tolerance": self._mass_tolerance},
        )
        for r in mass_records:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-ASM-004",
                severity=Severity.WARNING,
                message=f"Mass roll-up inconsistency in assembly '{r['name']}': "
                        f"declared {r['total_mass']:.2f} kg vs children sum {r['child_sum']:.2f} kg",
                component_path=f"assembly/{r['name']}",
                details={"total_mass": r["total_mass"], "child_sum": r["child_sum"]},
            ))

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        has_warnings = any(v.severity == Severity.WARNING for v in violations)

        if has_errors:
            status = AnalysisStatus.FAIL
        elif has_warnings:
            status = AnalysisStatus.WARN
        else:
            status = AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="assembly_validator",
            status=status,
            violations=violations,
            summary={
                "checks_run": 4,
                "cycles": len(cycle_records),
                "orphans": len(orphan_records),
                "missing_materials": len(missing_mat_records),
                "mass_inconsistencies": len(mass_records),
            },
        )
