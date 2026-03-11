"""Electrical Agent - main analysis orchestrator for satellite electrical design."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..config import SatMaestroConfig
from ..core.graph_models import AnalysisResult, AnalysisStatus
from ..core.mcp_bridge import McpBridge
from ..core.report import ReportFormat, ReportGenerator
from .analyzers.pin_to_pin import PinToPinAnalyzer
from .analyzers.power_budget import PowerBudgetAnalyzer
from .analyzers.connector import ConnectorAnalyzer
from .rules.loader import RuleEngine

logger = logging.getLogger(__name__)


class ElectricalAgent:
    """Orchestrates electrical analysis of satellite designs.

    Coordinates parsers, analyzers, and rule engine to provide
    comprehensive electrical verification.
    """

    def __init__(self, bridge: McpBridge, config: SatMaestroConfig) -> None:
        self._bridge = bridge
        self._config = config
        self._report = ReportGenerator(config)

        # Initialize analyzers
        self.pin_to_pin = PinToPinAnalyzer(self._bridge)
        self.power_budget = PowerBudgetAnalyzer(self._bridge, config.derating_factor)
        self.connector = ConnectorAnalyzer(self._bridge, config.derating_factor)
        self.rule_engine = RuleEngine(self._bridge)

    async def run_full_analysis(
        self,
        subsystem: str | None = None,
        report_format: str = "cli",
    ) -> tuple[list[AnalysisResult], str]:
        """Run all electrical analyses and generate report.

        Returns tuple of (results list, report output).
        """
        logger.info("Starting full electrical analysis (subsystem=%s)", subsystem)
        results: list[AnalysisResult] = []

        # 1. Pin-to-pin verification
        try:
            pin_result = await self.pin_to_pin.verify(subsystem)
            results.append(pin_result)
            logger.info("Pin-to-pin: %s (%d violations)", pin_result.status.value, len(pin_result.violations))
        except Exception as e:
            logger.error("Pin-to-pin analysis failed: %s", e)
            results.append(AnalysisResult(
                analyzer="pin_to_pin",
                status=AnalysisStatus.FAIL,
                summary={"error": str(e)},
            ))

        # 2. Power budget analysis
        try:
            power_result = await self.power_budget.analyze(subsystem)
            results.append(power_result)
            logger.info("Power budget: %s (%d violations)", power_result.status.value, len(power_result.violations))
        except Exception as e:
            logger.error("Power budget analysis failed: %s", e)
            results.append(AnalysisResult(
                analyzer="power_budget",
                status=AnalysisStatus.FAIL,
                summary={"error": str(e)},
            ))

        # 3. Connector check
        try:
            conn_result = await self.connector.check(subsystem)
            results.append(conn_result)
            logger.info("Connector check: %s (%d violations)", conn_result.status.value, len(conn_result.violations))
        except Exception as e:
            logger.error("Connector analysis failed: %s", e)
            results.append(AnalysisResult(
                analyzer="connector",
                status=AnalysisStatus.FAIL,
                summary={"error": str(e)},
            ))

        # 4. ECSS compliance check
        try:
            violations = await self.rule_engine.run_all(subsystem)
            ecss_status = AnalysisStatus.FAIL if any(
                v.severity.value == "ERROR" for v in violations
            ) else AnalysisStatus.WARN if violations else AnalysisStatus.PASS

            results.append(AnalysisResult(
                analyzer="ecss_compliance",
                status=ecss_status,
                violations=violations,
                summary={"rules_checked": len(await self.rule_engine.load_rules())},
            ))
            logger.info("ECSS compliance: %s (%d violations)", ecss_status.value, len(violations))
        except Exception as e:
            logger.error("ECSS compliance check failed: %s", e)
            results.append(AnalysisResult(
                analyzer="ecss_compliance",
                status=AnalysisStatus.FAIL,
                summary={"error": str(e)},
            ))

        # Generate report
        run_id = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        report_output = await self._report.generate(results, report_format, run_id=run_id)

        # Store results in Neo4j via MCP bridge
        try:
            for result in results:
                store_id = f"{run_id}-{result.analyzer}"
                await self._bridge.neo4j_write(
                    "CREATE (run:AnalysisRun {id: $id, analyzer: $analyzer, "
                    "status: $status, timestamp: $timestamp}) RETURN run.id AS id",
                    {
                        "id": store_id,
                        "analyzer": result.analyzer,
                        "status": result.status.value,
                        "timestamp": result.timestamp.isoformat(),
                    },
                )
                for v in result.violations:
                    await self._bridge.neo4j_write(
                        "MATCH (run:AnalysisRun {id: $run_id}) "
                        "CREATE (v:Violation {rule_id: $rule_id, severity: $severity, "
                        "message: $message, component_path: $component_path}) "
                        "CREATE (run)-[:FOUND]->(v)",
                        {
                            "run_id": store_id,
                            "rule_id": v.rule_id,
                            "severity": v.severity.value,
                            "message": v.message,
                            "component_path": v.component_path,
                        },
                    )
        except Exception as e:
            logger.warning("Could not store analysis run in Neo4j: %s", e)

        return results, report_output

    @property
    def bridge(self) -> McpBridge:
        """Access MCP bridge for direct queries."""
        return self._bridge
