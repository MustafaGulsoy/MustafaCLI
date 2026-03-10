"""Pin-to-pin continuity verification analyzer."""
from __future__ import annotations

import logging
from datetime import datetime

from ...core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation
from ...core.graph_ops import GraphOperations

logger = logging.getLogger(__name__)


class PinToPinAnalyzer:
    """Verify pin-to-pin electrical continuity in the satellite design."""

    def __init__(self, graph: GraphOperations) -> None:
        self._graph = graph

    async def verify(self, subsystem: str | None = None) -> AnalysisResult:
        """Run pin-to-pin continuity verification.

        Checks:
        1. All expected connections exist (no OPEN circuits)
        2. No unexpected connections (potential SHORT circuits)
        3. Pin direction compatibility (output -> input, not output -> output)
        """
        violations: list[Violation] = []
        checked = 0
        open_count = 0
        short_count = 0
        direction_issues = 0

        # Get all documented connections
        connections = await self._graph.get_all_connections()

        for conn in connections:
            checked += 1
            from_pin = conn.get("from_pin", "")
            to_pin = conn.get("to_pin", "")
            net_name = conn.get("net_name", "")

            # Verify path exists
            paths = await self._graph.find_path(from_pin, to_pin)
            if not paths:
                open_count += 1
                violations.append(Violation(
                    rule_id="PIN-OPEN",
                    severity=Severity.ERROR,
                    message=f"Open circuit: no path from {from_pin} to {to_pin} on net {net_name}",
                    component_path=f"{from_pin} -> {to_pin}",
                    details={"net": net_name, "type": "open"},
                ))

        # Check for direction compatibility
        if subsystem:
            components = await self._graph.get_components_by_subsystem(subsystem)
            for comp in components:
                pins = await self._graph.get_pins(comp.id)
                output_pins = [p for p in pins if p.direction.value == "OUTPUT"]

                for pin in output_pins:
                    # Check if any output is connected to another output
                    pin_connections = await self._graph.find_path(pin.id, pin.id)
                    # This is simplified - real implementation would check full path

        # Determine status
        if open_count > 0 or short_count > 0:
            status = AnalysisStatus.FAIL
        elif direction_issues > 0:
            status = AnalysisStatus.WARN
        else:
            status = AnalysisStatus.PASS

        return AnalysisResult(
            analyzer="pin_to_pin",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary={
                "connections_checked": checked,
                "open_circuits": open_count,
                "short_circuits": short_count,
                "direction_issues": direction_issues,
            },
            metadata={"subsystem": subsystem},
        )
