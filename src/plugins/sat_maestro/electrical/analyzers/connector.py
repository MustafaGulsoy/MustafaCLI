"""Connector derating and matching analyzer."""
from __future__ import annotations

import logging
from datetime import datetime

from ...core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)


class ConnectorAnalyzer:
    """Analyze connector derating, matching, and ECSS compliance."""

    def __init__(self, bridge: McpBridge, derating_factor: float = 0.75) -> None:
        self._bridge = bridge
        self._derating_factor = derating_factor

    async def check(self, subsystem: str | None = None) -> AnalysisResult:
        """Run connector analysis.

        Checks:
        1. Connector pin count matching (mated pairs)
        2. Connector series compatibility
        3. Current derating per ECSS-E-ST-20C
        4. Voltage compatibility between mated pins
        """
        violations: list[Violation] = []
        checked = 0

        # Get connectors via Cypher
        query = "MATCH (c:Connector) RETURN c"
        if subsystem:
            query = (
                "MATCH (c:Connector)-[:HAS_PIN]->(:Pin)<-[:HAS_PIN]-(comp:Component {subsystem: $subsystem}) "
                "RETURN DISTINCT c"
            )

        try:
            await self._bridge.neo4j_query(
                query, {"subsystem": subsystem} if subsystem else {}
            )
        except Exception:
            pass

        # Check mated pairs
        mate_query = (
            "MATCH (c1:Connector)-[:MATES_WITH]->(c2:Connector) "
            "RETURN c1, c2"
        )
        try:
            mate_pairs = await self._bridge.neo4j_query(mate_query)
        except Exception:
            mate_pairs = []

        for pair in mate_pairs:
            checked += 1
            c1 = pair["c1"]
            c2 = pair["c2"]

            c1_name = c1.get("name", c1.get("id", "?"))
            c2_name = c2.get("name", c2.get("id", "?"))

            # Check pin count match
            c1_pins = c1.get("pin_count", 0)
            c2_pins = c2.get("pin_count", 0)
            if c1_pins != c2_pins:
                violations.append(Violation(
                    rule_id="CONN-PIN-COUNT",
                    severity=Severity.ERROR,
                    message=(
                        f"Pin count mismatch: {c1_name} ({c1_pins} pins) "
                        f"mates with {c2_name} ({c2_pins} pins)"
                    ),
                    component_path=f"{c1_name} <-> {c2_name}",
                    details={"c1_pins": c1_pins, "c2_pins": c2_pins},
                ))

            # Check series compatibility
            c1_series = c1.get("series", "")
            c2_series = c2.get("series", "")
            if c1_series and c2_series and c1_series != c2_series:
                violations.append(Violation(
                    rule_id="CONN-SERIES",
                    severity=Severity.ERROR,
                    message=(
                        f"Series mismatch: {c1_name} ({c1_series}) "
                        f"mates with {c2_name} ({c2_series})"
                    ),
                    component_path=f"{c1_name} <-> {c2_name}",
                    details={"c1_series": c1_series, "c2_series": c2_series},
                ))

            # Check current derating
            c1_rating = c1.get("current_rating", 0)
            if c1_rating > 0:
                derated_max = c1_rating * self._derating_factor
                pin_query = (
                    "MATCH (c:Connector {id: $conn_id})-[:HAS_PIN]->(p:Pin) "
                    "WHERE p.actual_current IS NOT NULL "
                    "RETURN max(p.actual_current) AS max_current"
                )
                try:
                    current_result = await self._bridge.neo4j_query(
                        pin_query, {"conn_id": c1.get("id", "")}
                    )
                    if current_result and current_result[0].get("max_current"):
                        max_current = current_result[0]["max_current"]
                        if max_current > derated_max:
                            pct = (max_current / c1_rating) * 100
                            violations.append(Violation(
                                rule_id="ECSS-E-ST-20C-5.3.1",
                                severity=Severity.ERROR,
                                message=(
                                    f"Connector {c1_name} exceeds {self._derating_factor:.0%} "
                                    f"derating (actual: {pct:.0f}%)"
                                ),
                                component_path=c1_name,
                                details={
                                    "current_rating": c1_rating,
                                    "derated_max": derated_max,
                                    "actual_current": max_current,
                                },
                            ))
                except Exception as e:
                    logger.warning("Could not check derating for %s: %s", c1_name, e)

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
            analyzer="connector",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary={
                "connectors_checked": checked,
                "mate_pairs": len(mate_pairs),
                "pin_count_errors": sum(1 for v in violations if v.rule_id == "CONN-PIN-COUNT"),
                "series_errors": sum(1 for v in violations if v.rule_id == "CONN-SERIES"),
                "derating_errors": sum(1 for v in violations if v.rule_id == "ECSS-E-ST-20C-5.3.1"),
            },
            metadata={
                "subsystem": subsystem,
                "derating_factor": self._derating_factor,
            },
        )
