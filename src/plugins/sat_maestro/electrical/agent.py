"""Electrical Agent - main analysis orchestrator for satellite electrical design."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..config import SatMaestroConfig
from ..core.graph_models import AnalysisResult, AnalysisStatus
from ..core.graph_ops import GraphOperations
from ..core.neo4j_client import Neo4jClient
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

    def __init__(self, neo4j: Neo4jClient, config: SatMaestroConfig) -> None:
        self._graph = GraphOperations(neo4j)
        self._config = config
        self._report = ReportGenerator(config)

        # Initialize analyzers
        self.pin_to_pin = PinToPinAnalyzer(self._graph)
        self.power_budget = PowerBudgetAnalyzer(self._graph, config.derating_factor)
        self.connector = ConnectorAnalyzer(self._graph, config.derating_factor)
        self.rule_engine = RuleEngine(self._graph)

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

        # Store results in Neo4j
        try:
            for result in results:
                await self._graph.store_analysis_run(result, f"{run_id}-{result.analyzer}")
        except Exception as e:
            logger.warning("Could not store analysis run in Neo4j: %s", e)

        return results, report_output

    @property
    def graph(self) -> GraphOperations:
        """Access graph operations for direct queries."""
        return self._graph
