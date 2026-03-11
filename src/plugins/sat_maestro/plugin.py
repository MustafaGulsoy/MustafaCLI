"""SAT-MAESTRO Plugin - Main entry point for MustafaCLI plugin system."""
from __future__ import annotations

import json
import logging
from typing import Any

from ..base import PluginBase, PluginMetadata, plugin_tool
from ...core.tools import ToolResult
from .config import SatMaestroConfig
from .core.mcp_bridge import McpBridge, McpServerConfig
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

        # Initialize MCP Bridge
        self._bridge = McpBridge({
            "neo4j": McpServerConfig(name="neo4j", command="neo4j-mcp"),
            "gmsh": McpServerConfig(name="gmsh", command=self.config.gmsh_mcp_command),
            "calculix": McpServerConfig(name="calculix", command=self.config.calculix_path),
        })

        # Initialize Electrical Agent with MCP bridge
        from .electrical.agent import ElectricalAgent
        self.electrical = ElectricalAgent(self._bridge, self.config)

        # Initialize Mechanical Agent
        from .mechanical.agent import MechanicalAgent
        self.mechanical = MechanicalAgent(self._bridge, self.config)

        logger.info("SAT-MAESTRO: Plugin initialized successfully")

    async def shutdown(self) -> None:
        """Close Neo4j connection and disconnect MCP servers."""
        if hasattr(self, '_bridge'):
            await self._bridge.disconnect_all()
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

    # -- Import Tools --

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
                total_pads = 0
                total_traces = 0
                for r in results:
                    layer = r.layers[0] if r.layers else ""
                    for pad in r.pads:
                        pad.layer = layer
                        await self._graph.create_pad(pad)
                        total_pads += 1
                    for trace in r.traces:
                        trace.layer = layer
                        await self._graph.create_trace(trace)
                        total_traces += 1
                output = (
                    f"Imported Gerber directory: {file_path}\n"
                    f"  Files: {len(results)}\n"
                    f"  Pads loaded to Neo4j: {total_pads}\n"
                    f"  Traces loaded to Neo4j: {total_traces}"
                )
            else:
                result = parser.parse(file_path)
                for pad in result.pads:
                    await self._graph.create_pad(pad)
                for trace in result.traces:
                    await self._graph.create_trace(trace)
                output = (
                    f"Imported Gerber file: {file_path}\n"
                    f"  Pads loaded to Neo4j: {len(result.pads)}\n"
                    f"  Traces loaded to Neo4j: {len(result.traces)}\n"
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

    # -- Analysis Tools --

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

    # -- Mechanical Import Tools --

    @plugin_tool(
        name="sat_import_step",
        description="Import a STEP CAD file and generate FEM mesh via Gmsh MCP",
    )
    async def import_step(self, file_path: str, element_size: float = 5.0) -> ToolResult:
        """Import STEP file and mesh it using Gmsh."""
        try:
            result = await self._bridge.call_tool("gmsh", "gmsh_mesh_from_step", {
                "step_file": file_path, "element_size": element_size,
            })
            return ToolResult(success=True, output=json.dumps(result, indent=2, default=str))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # -- Mechanical Structural Tools --

    @plugin_tool(
        name="sat_mass_budget",
        description="Run mass budget analysis against allocation with ECSS margins",
    )
    async def mass_budget(self, budget: float = 100.0, subsystem: str = "") -> ToolResult:
        """Analyze mass budget for the spacecraft."""
        if err := self._check_connected():
            return err
        try:
            result = await self.mechanical.mass_budget.analyze(budget, subsystem or None)
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_cog_analysis",
        description="Calculate spacecraft center of gravity and check offset limits",
    )
    async def cog_analysis(self, max_offset: float = 0.0, subsystem: str = "") -> ToolResult:
        """Calculate CoG and validate against offset limits."""
        if err := self._check_connected():
            return err
        try:
            result = await self.mechanical.cog.calculate(
                subsystem=subsystem or None,
                max_offset=max_offset if max_offset > 0 else None,
            )
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_structural_analyze",
        description="Run structural analysis (mass budget, CoG, assembly validation)",
    )
    async def structural_analyze(self, budget: float = 100.0, max_cog_offset: float = 0.0) -> ToolResult:
        """Run all structural analyses."""
        if err := self._check_connected():
            return err
        try:
            results, summary = await self.mechanical.run_structural(
                mass_budget=budget,
                max_cog_offset=max_cog_offset if max_cog_offset > 0 else None,
            )
            return ToolResult(success=True, output=summary)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # -- Mechanical Thermal Tools --

    @plugin_tool(
        name="sat_thermal_import",
        description="Import thermal node definitions into the knowledge graph",
    )
    async def thermal_import(self, nodes_json: str) -> ToolResult:
        """Import thermal node data (JSON string with node definitions)."""
        if err := self._check_connected():
            return err
        try:
            nodes = json.loads(nodes_json)
            for node in nodes:
                await self._bridge.neo4j_write(
                    "CREATE (n:ThermalNode {name: $name, temperature: $temp, capacity: $cap})",
                    {"name": node["name"], "temp": node.get("temperature", 293.0),
                     "cap": node.get("capacity", 1.0)},
                )
            return ToolResult(success=True, output=f"Imported {len(nodes)} thermal nodes")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_thermal_solve",
        description="Run lumped-parameter thermal analysis on the satellite model",
    )
    async def thermal_solve(self) -> ToolResult:
        """Run thermal node model solver."""
        if err := self._check_connected():
            return err
        try:
            result = await self.mechanical.thermal_solver.analyze()
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_thermal_check",
        description="Check component temperatures against ECSS qualification limits",
    )
    async def thermal_check(self) -> ToolResult:
        """Validate temperatures against limits."""
        if err := self._check_connected():
            return err
        try:
            result = await self.mechanical.thermal_checker.analyze()
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_thermal_orbital",
        description="Analyze orbital thermal cycle (hot/cold case with eclipse)",
    )
    async def thermal_orbital(self, orbit_period: float = 5400.0,
                              eclipse_fraction: float = 0.35) -> ToolResult:
        """Run orbital thermal cycle analysis."""
        if err := self._check_connected():
            return err
        try:
            result = await self.mechanical.orbital_cycle.analyze(
                orbit_period=orbit_period, eclipse_fraction=eclipse_fraction,
            )
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # -- Mechanical Mechanism Tools --

    @plugin_tool(
        name="sat_mechanism_define",
        description="Define a deployable mechanism (solar array, antenna, etc.)",
    )
    async def mechanism_define(self, mechanism_json: str) -> ToolResult:
        """Define a mechanism in the knowledge graph."""
        if err := self._check_connected():
            return err
        try:
            mech = json.loads(mechanism_json)
            await self._bridge.neo4j_write(
                "CREATE (m:Mechanism {name: $name, type: $type, "
                "stowed_angle: $stowed, deployed_angle: $deployed})",
                {"name": mech["name"], "type": mech.get("type", "hinge"),
                 "stowed": mech.get("stowed_angle", 0.0),
                 "deployed": mech.get("deployed_angle", 180.0)},
            )
            return ToolResult(success=True, output=f"Defined mechanism: {mech['name']}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_deployment_verify",
        description="Verify deployment sequence and mechanism kinematics",
    )
    async def deployment_verify(self) -> ToolResult:
        """Run deployment sequence validation."""
        if err := self._check_connected():
            return err
        try:
            result = await self.mechanical.deployment.validate()
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_kinematic_check",
        description="Run kinematic and kinetic analysis on mechanisms",
    )
    async def kinematic_check(self) -> ToolResult:
        """Run kinematic/kinetic analysis."""
        if err := self._check_connected():
            return err
        try:
            result = await self.mechanical.kinematic.analyze()
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # -- Mechanical Vibration Tools --

    @plugin_tool(
        name="sat_modal_analyze",
        description="Evaluate modal analysis results against ECSS frequency requirements",
    )
    async def modal_analyze(self, modes_json: str = "",
                            min_lateral_hz: float = 0.0,
                            min_axial_hz: float = 0.0) -> ToolResult:
        """Run modal frequency evaluation."""
        try:
            modes = json.loads(modes_json) if modes_json else []
            result = await self.mechanical.modal.evaluate(
                modes,
                min_lateral_hz=min_lateral_hz or self.config.min_lateral_freq,
                min_axial_hz=min_axial_hz or self.config.min_axial_freq,
            )
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_random_vib",
        description="Run random vibration analysis (PSD input, gRMS output)",
    )
    async def random_vib(self, psd_json: str, grms_limit: float = 0.0) -> ToolResult:
        """Analyze random vibration from PSD profile."""
        try:
            psd_profile = json.loads(psd_json)
            result = await self.mechanical.random_vib.analyze(
                psd_profile, grms_limit=grms_limit if grms_limit > 0 else None,
            )
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @plugin_tool(
        name="sat_shock_analyze",
        description="Compare shock response spectrum (SRS) against qualification levels",
    )
    async def shock_analyze(self, srs_json: str, qual_json: str,
                            margin_db: float = 3.0) -> ToolResult:
        """Run SRS shock analysis."""
        try:
            srs_data = json.loads(srs_json)
            qual_levels = json.loads(qual_json)
            result = await self.mechanical.shock.evaluate(srs_data, qual_levels, margin_db)
            return ToolResult(
                success=result.status.value != "FAIL",
                output=json.dumps({"status": result.status.value, **result.summary}, indent=2, default=str),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # -- Cross-Discipline Tools --

    @plugin_tool(
        name="sat_cross_check",
        description="Run cross-discipline checks (mass-thermal, electrical-thermal, harness)",
    )
    async def cross_check(self, checks: str = "all") -> ToolResult:
        """Run cross-discipline analysis checks."""
        if err := self._check_connected():
            return err
        try:
            from .cross_discipline.mass_thermal import MassThermalAnalyzer
            from .cross_discipline.electrical_thermal import ElectricalThermalAnalyzer
            from .cross_discipline.harness_routing import HarnessRoutingAnalyzer

            results = []
            analyzers = {
                "mass_thermal": MassThermalAnalyzer(self._bridge),
                "electrical_thermal": ElectricalThermalAnalyzer(self._bridge),
                "harness": HarnessRoutingAnalyzer(self._bridge),
            }

            selected = analyzers if checks == "all" else {
                k: v for k, v in analyzers.items() if k in checks.split(",")
            }

            for name, analyzer in selected.items():
                result = await analyzer.analyze()
                results.append({"analyzer": name, "status": result.status.value,
                                "violations": len(result.violations)})

            return ToolResult(
                success=True,
                output=json.dumps({"cross_discipline_results": results}, indent=2),
            )
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
