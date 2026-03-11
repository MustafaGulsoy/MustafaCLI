"""Cross-Discipline Agent — orchestrates all cross-discipline checks."""
from __future__ import annotations

import logging
from typing import Any

from ..core.graph_models import AnalysisResult, AnalysisStatus
from ..core.mcp_bridge import McpBridge
from .mass_thermal import MassThermalAnalyzer
from .electrical_thermal import ElectricalThermalAnalyzer
from .harness_routing import HarnessRoutingAnalyzer
from .mounting_check import MountingCheckAnalyzer

logger = logging.getLogger(__name__)


class CrossDisciplineAgent:
    """Orchestrates cross-discipline analysis between electrical, mechanical, and thermal domains."""

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge
        self.mass_thermal = MassThermalAnalyzer(bridge)
        self.electrical_thermal = ElectricalThermalAnalyzer(bridge)
        self.harness_routing = HarnessRoutingAnalyzer(bridge)
        self.mounting_check = MountingCheckAnalyzer(bridge)

    async def run_all(self) -> list[AnalysisResult]:
        """Run all cross-discipline checks and return results."""
        results: list[AnalysisResult] = []

        analyzers = [
            self.mass_thermal,
            self.electrical_thermal,
            self.harness_routing,
            self.mounting_check,
        ]

        for analyzer in analyzers:
            try:
                result = await analyzer.analyze()
                results.append(result)
            except Exception as e:
                logger.error("Cross-discipline analyzer %s failed: %s",
                             type(analyzer).__name__, e)
                results.append(AnalysisResult(
                    analyzer=type(analyzer).__name__,
                    status=AnalysisStatus.FAIL,
                    summary={"error": str(e)},
                ))

        return results
