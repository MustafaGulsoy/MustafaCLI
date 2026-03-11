"""Center of gravity calculation for satellite assemblies."""
from __future__ import annotations

import math
import logging
from typing import TYPE_CHECKING

from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation

if TYPE_CHECKING:
    from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)


class CogCalculator:
    """Calculate spacecraft center of gravity from structure masses and positions."""

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    async def calculate(self, subsystem: str | None = None,
                        max_offset: float | None = None) -> AnalysisResult:
        """Calculate CoG and check against offset limits."""
        violations: list[Violation] = []

        query = """
        MATCH (s:Structure)
        RETURN s.mass AS mass, s.cog_x AS cog_x, s.cog_y AS cog_y, s.cog_z AS cog_z
        """
        if subsystem:
            query = f"""
            MATCH (s:Structure {{subsystem: '{subsystem}'}})
            RETURN s.mass AS mass, s.cog_x AS cog_x, s.cog_y AS cog_y, s.cog_z AS cog_z
            """

        records = await self._bridge.neo4j_query(query)

        total_mass = 0.0
        mx = my = mz = 0.0

        for r in records:
            m = r.get("mass", 0.0) or 0.0
            total_mass += m
            mx += m * (r.get("cog_x", 0.0) or 0.0)
            my += m * (r.get("cog_y", 0.0) or 0.0)
            mz += m * (r.get("cog_z", 0.0) or 0.0)

        if total_mass > 0:
            cog_x = mx / total_mass
            cog_y = my / total_mass
            cog_z = mz / total_mass
        else:
            cog_x = cog_y = cog_z = 0.0

        offset = math.sqrt(cog_x**2 + cog_y**2 + cog_z**2)

        if max_offset is not None and offset > max_offset:
            violations.append(Violation(
                rule_id="ECSS-E-ST-32C-COG-001",
                severity=Severity.ERROR,
                message=f"CoG offset {offset:.3f} m exceeds limit {max_offset:.3f} m",
                component_path="spacecraft",
                details={"offset": offset, "limit": max_offset},
            ))

        status = AnalysisStatus.FAIL if violations else AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="cog_analysis",
            status=status,
            violations=violations,
            summary={
                "cog_x": cog_x, "cog_y": cog_y, "cog_z": cog_z,
                "offset": offset, "total_mass": total_mass,
            },
        )
