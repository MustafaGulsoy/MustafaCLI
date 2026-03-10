"""SAT-MAESTRO Plugin - Main entry point for MustafaCLI plugin system."""
from __future__ import annotations

import logging
from typing import Any

from ..base import PluginBase, PluginMetadata, plugin_tool
from ...core.tools import ToolResult
from .config import SatMaestroConfig
from .core.neo4j_client import Neo4jClient
from .core.graph_ops import GraphOperations
from .core.report import ReportFormat, ReportGenerator
from .db.seed_rules import seed_default_rules

logger = logging.getLogger(__name__)


class SatMaestroPlugin(PluginBase):
    """SAT-MAESTRO: Satellite Multidisciplinary Engineering & System Trust Officer.

    Optional plugin providing satellite electrical engineering analysis
    via Neo4j knowledge graph. Activate with: mustafacli plugin enable sat-maestro
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="sat-maestro",
            version="0.1.0",
            description="Satellite Engineering Analysis - Electrical Agent",
            author="Kardelen Yazilim",
            requires=["neo4j", "pygerber", "sexpdata", "jinja2"],
            tags=["satellite", "electrical", "ecss", "engineering"],
            homepage="https://github.com/kardelenyazilim/sat-maestro",
            license="MIT",
        )

    async def initialize(self) -> None:
        """Initialize Neo4j connection and seed ECSS rules."""
        self.config = SatMaestroConfig.from_env()
        self.neo4j = Neo4jClient(self.config)

        try:
            await self.neo4j.connect()
            logger.info("SAT-MAESTRO: Connected to Neo4j at %s", self.config.neo4j_uri)
        except Exception as e:
            logger.error("SAT-MAESTRO: Failed to connect to Neo4j: %s", e)
            logger.info("SAT-MAESTRO: Plugin loaded but Neo4j features unavailable. "
                        "Start Neo4j with: docker compose -f deployment/docker-compose.sat-maestro.yml up -d")
            self.neo4j = None
            return

        self._graph = GraphOperations(self.neo4j)
        self._report = ReportGenerator(self.config)

        # Seed default ECSS rules
        try:
            count = await seed_default_rules(self._graph)
            if count > 0:
                logger.info("SAT-MAESTRO: Seeded %d ECSS rules", count)
        except Exception as e:
            logger.warning("SAT-MAESTRO: Could not seed rules: %s", e)

        # Initialize Electrical Agent
        from .electrical.agent import ElectricalAgent
        self.electrical = ElectricalAgent(self.neo4j, self.config)

        logger.info("SAT-MAESTRO: Plugin initialized successfully")

    async def shutdown(self) -> None:
        """Close Neo4j connection."""
        if self.neo4j:
            await self.neo4j.close()
            logger.info("SAT-MAESTRO: Shutdown complete")

    def _check_connected(self) -> ToolResult | None:
        """Return error ToolResult if Neo4j is not connected, else None."""
        if not self.neo4j or not self.neo4j.is_connected:
            return ToolResult(
                success=False,
                output="",
                error="Neo4j not connected. Start with: docker compose -f deployment/docker-compose.sat-maestro.yml up -d",
            )
        return None

    # ── Import Tools ──────────────────────────────────────────────

    @plugin_tool(
        name="sat_import_kicad",
        description="Import a KiCad schematic/PCB project into the Neo4j knowledge graph",
    )
    async def import_kicad(self, file_path: str, subsystem: str = "default") -> ToolResult:
        """Parse KiCad file and load components/pins/nets into Neo4j."""
        if err := self._check_connected():
            return err

        try:
            from .electrical.parsers.kicad import KiCadParser
            parser = KiCadParser()
            result = parser.parse(file_path, subsystem)

            # Load into Neo4j
            for comp in result.components:
                await self._graph.create_component(comp)
            for pin in result.pins:
                if pin.component_id:
                    await self._graph.add_pin(pin.component_id, pin)
            for net in result.nets:
                await self._graph.create_net(net)

            output = (
                f"Imported KiCad file: {file_path}\n"
                f"  Components: {len(result.components)}\n"
                f"  Pins: {len(result.pins)}\n"
                f"  Nets: {len(result.nets)}\n"
                f"  Subsystem: {subsystem}"
            )
            if result.warnings:
                output += f"\n  Warnings: {len(result.warnings)}"
                for w in result.warnings:
                    output += f"\n    - {w}"

            return ToolResult(success=True, output=output)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_import_gerber",
        description="Import Gerber RS-274X PCB files into the knowledge graph",
    )
    async def import_gerber(self, file_path: str) -> ToolResult:
        """Parse Gerber file(s) and load pad/trace data into Neo4j."""
        if err := self._check_connected():
            return err

        try:
            from .electrical.parsers.gerber import GerberParser
            parser = GerberParser()

            import os
            if os.path.isdir(file_path):
                results = parser.parse_directory(file_path)
                total_pads = sum(len(r.pads) for r in results)
                total_traces = sum(len(r.traces) for r in results)
                output = (
                    f"Imported Gerber directory: {file_path}\n"
                    f"  Files: {len(results)}\n"
                    f"  Pads: {total_pads}\n"
                    f"  Traces: {total_traces}"
                )
            else:
                result = parser.parse(file_path)
                output = (
                    f"Imported Gerber file: {file_path}\n"
                    f"  Pads: {len(result.pads)}\n"
                    f"  Traces: {len(result.traces)}\n"
                    f"  Apertures: {len(result.apertures)}"
                )

            return ToolResult(success=True, output=output)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_analyze_pdf",
        description="Analyze a PDF schematic using LLM vision to extract components and connections",
    )
    async def analyze_pdf(self, file_path: str, subsystem: str = "default") -> ToolResult:
        """Analyze PDF schematic via LLM vision and load into Neo4j."""
        if err := self._check_connected():
            return err

        try:
            from .electrical.parsers.pdf_vision import PdfVisionParser
            parser = PdfVisionParser(self.config)
            result = await parser.parse(file_path, subsystem)

            # Load into Neo4j
            for comp in result.components:
                await self._graph.create_component(comp)
            for pin in result.pins:
                if pin.component_id:
                    await self._graph.add_pin(pin.component_id, pin)
            for net in result.nets:
                await self._graph.create_net(net)

            output = (
                f"PDF Vision Analysis: {file_path}\n"
                f"  Components: {len(result.components)}\n"
                f"  Pins: {len(result.pins)}\n"
                f"  Nets: {len(result.nets)}\n"
                f"  Confidence: {result.confidence:.0%}"
            )
            if result.warnings:
                output += f"\n  Warnings:"
                for w in result.warnings:
                    output += f"\n    - {w}"

            return ToolResult(success=True, output=output)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── Analysis Tools ────────────────────────────────────────────

    @plugin_tool(
        name="sat_verify_pins",
        description="Run pin-to-pin continuity verification on the satellite design",
    )
    async def verify_pins(self, subsystem: str = "") -> ToolResult:
        """Verify all pin-to-pin connections in the knowledge graph."""
        if err := self._check_connected():
            return err

        try:
            result = await self.electrical.pin_to_pin.verify(subsystem or None)
            report = self._report._render_cli([result], "pin-check")
            return ToolResult(success=True, output=report)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_power_budget",
        description="Analyze power budget and margins for satellite subsystem",
    )
    async def power_budget(self, subsystem: str = "EPS") -> ToolResult:
        """Run power budget analysis with derating checks."""
        if err := self._check_connected():
            return err

        try:
            result = await self.electrical.power_budget.analyze(subsystem)
            report = self._report._render_cli([result], "power-budget")
            return ToolResult(success=True, output=report)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_check_connectors",
        description="Check connector derating, matching, and ECSS compliance",
    )
    async def check_connectors(self, subsystem: str = "") -> ToolResult:
        """Run connector analysis."""
        if err := self._check_connected():
            return err

        try:
            result = await self.electrical.connector.check(subsystem or None)
            report = self._report._render_cli([result], "connector-check")
            return ToolResult(success=True, output=report)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_check_compliance",
        description="Run all ECSS compliance rules and generate full report",
    )
    async def check_compliance(self, subsystem: str = "", format: str = "cli") -> ToolResult:
        """Run full ECSS compliance check with all analyzers."""
        if err := self._check_connected():
            return err

        try:
            results, report = await self.electrical.run_full_analysis(
                subsystem=subsystem or None,
                report_format=format,
            )
            return ToolResult(success=True, output=report)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_report",
        description="Generate analysis report in specified format (cli, json, html, all)",
    )
    async def generate_report(self, format: str = "cli", subsystem: str = "") -> ToolResult:
        """Generate report from latest analysis results."""
        if err := self._check_connected():
            return err

        try:
            results, report = await self.electrical.run_full_analysis(
                subsystem=subsystem or None,
                report_format=format,
            )
            return ToolResult(success=True, output=report)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_graph_query",
        description="Execute a custom Cypher query on the satellite knowledge graph",
    )
    async def graph_query(self, query: str) -> ToolResult:
        """Run a custom Cypher query and return results."""
        if err := self._check_connected():
            return err

        try:
            import json
            results = await self.neo4j.execute(query)
            output = json.dumps(results, indent=2, default=str)
            return ToolResult(success=True, output=f"Query returned {len(results)} records:\n{output}")

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Cypher query error: {e}")

    @plugin_tool(
        name="sat_seed_rules",
        description="Load custom ECSS rules from a JSON file into the knowledge graph",
    )
    async def seed_rules(self, file_path: str = "") -> ToolResult:
        """Seed ECSS rules - defaults or from custom JSON file."""
        if err := self._check_connected():
            return err

        try:
            if file_path:
                import json
                from pathlib import Path
                from .core.graph_models import EcssRule, Severity

                data = json.loads(Path(file_path).read_text(encoding="utf-8"))
                rules = [
                    EcssRule(
                        id=r["id"],
                        standard=r["standard"],
                        clause=r["clause"],
                        severity=Severity(r["severity"]),
                        category=r["category"],
                        check_expression=r["check_expression"],
                        message_template=r["message_template"],
                    )
                    for r in data
                ]
                count = await self._graph.load_ecss_rules(rules)
            else:
                count = await seed_default_rules(self._graph)

            return ToolResult(
                success=True,
                output=f"Seeded {count} ECSS rules into knowledge graph",
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
