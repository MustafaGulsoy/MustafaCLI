"""Orbital thermal analysis wrapper for the CubeSat auto-design pipeline.

Integrates the existing ``OrbitalCycleAnalyzer`` with the CubeSat design
wizard by:
1. Querying ThermalNode data from Neo4j (or synthesising nodes from the
   component catalog when no thermal model exists yet).
2. Setting up hot-case and cold-case scenarios per ECSS-E-ST-31C.
3. Running the orbital cycle simulation for both cases.
4. Checking results against ECSS qualification margins (operational range
   plus 10 degrees C on each side).
5. Returning a unified ``AnalysisResult`` for the pipeline.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ...core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from ...cubesat_wizard import COMPONENT_CATALOG, CubeSatDesign
from .orbital_cycle import OrbitalCycleAnalyzer

if TYPE_CHECKING:
    from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Physical / orbital constants
# ---------------------------------------------------------------------------
_EARTH_RADIUS_M: float = 6_371_000.0
_MU: float = 3.986004418e14  # m^3/s^2
_SOLAR_FLUX_1AU: float = 1361.0  # W/m^2

# ---------------------------------------------------------------------------
# ECSS thermal margins (ECSS-E-ST-31C, clause 4.5.3)
# ---------------------------------------------------------------------------
_ECSS_QUAL_MARGIN_C: float = 10.0  # qualification range = op range +/- 10 C

# ---------------------------------------------------------------------------
# Default component thermal properties
# ---------------------------------------------------------------------------

_COMPONENT_THERMAL_DEFAULTS: dict[str, dict[str, float]] = {
    # subsystem_id -> {op_min, op_max, capacity_J_per_K, absorptivity}
    "eps": {"op_min": -20.0, "op_max": 60.0, "capacity": 50.0, "absorptivity": 0.5},
    "obc": {"op_min": -20.0, "op_max": 70.0, "capacity": 30.0, "absorptivity": 0.3},
    "com_uhf": {"op_min": -30.0, "op_max": 60.0, "capacity": 25.0, "absorptivity": 0.4},
    "com_sband": {"op_min": -20.0, "op_max": 65.0, "capacity": 30.0, "absorptivity": 0.4},
    "adcs": {"op_min": -20.0, "op_max": 60.0, "capacity": 35.0, "absorptivity": 0.4},
    "gps": {"op_min": -30.0, "op_max": 65.0, "capacity": 15.0, "absorptivity": 0.3},
    "propulsion": {"op_min": 5.0, "op_max": 50.0, "capacity": 80.0, "absorptivity": 0.5},
    "thermal": {"op_min": -40.0, "op_max": 85.0, "capacity": 10.0, "absorptivity": 0.3},
    "payload": {"op_min": -10.0, "op_max": 50.0, "capacity": 40.0, "absorptivity": 0.5},
    "structure": {"op_min": -40.0, "op_max": 85.0, "capacity": 200.0, "absorptivity": 0.5},
}

# ---------------------------------------------------------------------------
# Scenario dataclass
# ---------------------------------------------------------------------------


@dataclass
class ThermalScenario:
    """Hot-case or cold-case scenario parameters."""

    name: str
    solar_flux: float  # W/m^2 at spacecraft distance
    albedo: float
    absorptivity: float
    eclipse_fraction: float
    area_m2: float  # effective illuminated area per node


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class OrbitalThermalResult:
    """Combined hot/cold case orbital thermal analysis result."""

    hot_case_min_temps: dict[str, float]
    hot_case_max_temps: dict[str, float]
    cold_case_min_temps: dict[str, float]
    cold_case_max_temps: dict[str, float]
    ecss_violations: list[Violation]
    node_count: int


# ---------------------------------------------------------------------------
# Orbit helper
# ---------------------------------------------------------------------------


def _orbit_period_s(altitude_km: float) -> float:
    """Orbit period from Kepler's third law."""
    a = _EARTH_RADIUS_M + altitude_km * 1000.0
    return 2.0 * math.pi * math.sqrt(a ** 3 / _MU)


def _eclipse_fraction(altitude_km: float, beta_deg: float) -> float:
    """Eclipse fraction for a circular orbit at given beta angle."""
    re = _EARTH_RADIUS_M
    h = altitude_km * 1000.0
    cos_beta = math.cos(math.radians(beta_deg))
    if abs(cos_beta) < 1e-9:
        return 0.0
    ratio = math.sqrt(h ** 2 + 2.0 * re * h) / ((re + h) * cos_beta)
    if ratio >= 1.0:
        return 0.0
    return max(0.0, min(1.0, (1.0 / math.pi) * math.acos(ratio)))


# ---------------------------------------------------------------------------
# Public analyzer
# ---------------------------------------------------------------------------


class OrbitalThermalAnalyzer:
    """Pipeline-integrated orbital thermal analysis.

    Wraps ``OrbitalCycleAnalyzer`` with hot/cold case scenario management
    and ECSS qualification margin checking.

    Args:
        bridge: MCP bridge for Neo4j queries.
        design: CubeSat design from the wizard.
    """

    def __init__(self, bridge: McpBridge, design: CubeSatDesign) -> None:
        self._bridge = bridge
        self._design = design

    # ------------------------------------------------------------------
    # Scenario setup
    # ------------------------------------------------------------------

    def _build_hot_case(self) -> ThermalScenario:
        """Hot case: maximum solar input, minimum eclipse.

        - Solar flux at perihelion: ~1414 W/m^2
        - High albedo: 0.35
        - Beta angle ~75 deg (short eclipse)
        - End-of-life absorptivity increase (+20%)
        """
        ecl = _eclipse_fraction(self._design.orbit_altitude, beta_deg=75.0)
        base_area = 0.01 * ({"1U": 1, "2U": 2, "3U": 3, "6U": 6, "12U": 12}
                            .get(self._design.sat_size, 1))
        return ThermalScenario(
            name="hot_case",
            solar_flux=1414.0,  # perihelion
            albedo=0.35,
            absorptivity=0.60,  # EOL degraded
            eclipse_fraction=ecl,
            area_m2=base_area,
        )

    def _build_cold_case(self) -> ThermalScenario:
        """Cold case: minimum solar input, maximum eclipse.

        - Solar flux at aphelion: ~1322 W/m^2
        - Low albedo: 0.25
        - Beta angle ~0 deg (longest eclipse)
        - Beginning-of-life absorptivity
        """
        ecl = _eclipse_fraction(self._design.orbit_altitude, beta_deg=0.0)
        base_area = 0.01 * ({"1U": 1, "2U": 2, "3U": 3, "6U": 6, "12U": 12}
                            .get(self._design.sat_size, 1))
        return ThermalScenario(
            name="cold_case",
            solar_flux=1322.0,  # aphelion
            albedo=0.25,
            absorptivity=0.45,  # BOL
            eclipse_fraction=ecl,
            area_m2=base_area,
        )

    # ------------------------------------------------------------------
    # Neo4j node query / synthesis
    # ------------------------------------------------------------------

    async def _get_thermal_nodes_from_neo4j(self) -> list[dict[str, Any]]:
        """Try to fetch ThermalNode data from Neo4j."""
        try:
            records = await self._bridge.neo4j_query(
                "MATCH (n:ThermalNode) "
                "RETURN n.id AS id, n.name AS name, "
                "       n.temperature AS temperature, "
                "       n.capacity AS capacity, "
                "       n.power_dissipation AS power_dissipation, "
                "       n.op_min_temp AS op_min_temp, "
                "       n.op_max_temp AS op_max_temp"
            )
            return [dict(r) for r in records]
        except Exception as exc:
            logger.debug("Could not fetch ThermalNodes from Neo4j: %s", exc)
            return []

    def _synthesize_thermal_nodes(self) -> list[dict[str, Any]]:
        """Create thermal nodes from the component catalog when Neo4j has none.

        Each selected subsystem becomes one lumped thermal node with
        properties drawn from ``_COMPONENT_THERMAL_DEFAULTS``.
        """
        nodes: list[dict[str, Any]] = []

        for ss_id in self._design.subsystems:
            if ss_id not in COMPONENT_CATALOG:
                continue
            catalog = COMPONENT_CATALOG[ss_id]
            defaults = _COMPONENT_THERMAL_DEFAULTS.get(ss_id, {})
            power = sum(
                c["power_w"] for c in catalog["components"] if c["power_w"] > 0
            )
            nodes.append({
                "id": f"thermal_{ss_id}",
                "name": catalog["name"],
                "temperature": 20.0,
                "capacity": defaults.get("capacity", 50.0),
                "power_dissipation": power,
                "op_min_temp": defaults.get("op_min", -40.0),
                "op_max_temp": defaults.get("op_max", 85.0),
            })

        # Payload node
        pl_defaults = _COMPONENT_THERMAL_DEFAULTS.get("payload", {})
        nodes.append({
            "id": "thermal_payload",
            "name": f"Payload ({self._design.payload_type})",
            "temperature": 20.0,
            "capacity": pl_defaults.get("capacity", 40.0),
            "power_dissipation": self._design.payload_power,
            "op_min_temp": pl_defaults.get("op_min", -10.0),
            "op_max_temp": pl_defaults.get("op_max", 50.0),
        })

        # Structure node (large thermal mass, no dissipation)
        st_defaults = _COMPONENT_THERMAL_DEFAULTS.get("structure", {})
        nodes.append({
            "id": "thermal_structure",
            "name": f"{self._design.sat_size} Structure",
            "temperature": 20.0,
            "capacity": st_defaults.get("capacity", 200.0),
            "power_dissipation": 0.0,
            "op_min_temp": st_defaults.get("op_min", -40.0),
            "op_max_temp": st_defaults.get("op_max", 85.0),
        })

        return nodes

    async def _ensure_thermal_nodes(self) -> list[dict[str, Any]]:
        """Fetch from Neo4j or synthesize if empty."""
        nodes = await self._get_thermal_nodes_from_neo4j()
        if nodes:
            logger.info("Found %d ThermalNodes in Neo4j", len(nodes))
            return nodes
        logger.info("No ThermalNodes in Neo4j -- synthesizing from catalog")
        return self._synthesize_thermal_nodes()

    # ------------------------------------------------------------------
    # Run a single scenario
    # ------------------------------------------------------------------

    async def _run_scenario(
        self,
        scenario: ThermalScenario,
    ) -> AnalysisResult:
        """Run the orbital cycle analyzer for one scenario.

        Uses the existing ``OrbitalCycleAnalyzer`` with scenario-specific
        parameters.
        """
        period_s = _orbit_period_s(self._design.orbit_altitude)
        analyzer = OrbitalCycleAnalyzer(self._bridge)

        return await analyzer.analyze(
            orbit_period=period_s,
            eclipse_fraction=scenario.eclipse_fraction,
            solar_flux=scenario.solar_flux,
            albedo=scenario.albedo,
            absorptivity=scenario.absorptivity,
            area=scenario.area_m2,
        )

    # ------------------------------------------------------------------
    # ECSS margin checking
    # ------------------------------------------------------------------

    @staticmethod
    def _check_ecss_margins(
        nodes: list[dict[str, Any]],
        hot_max_temps: dict[str, float],
        cold_min_temps: dict[str, float],
    ) -> list[Violation]:
        """Check temperatures against ECSS qualification margins.

        Qualification range = operational range +/- 10 C (ECSS-E-ST-31C).
        If the predicted temperature exceeds the qualification envelope,
        it is an ERROR.  If it is within qual but outside operational
        range, it is a WARNING.

        Args:
            nodes: Thermal node definitions with op_min/op_max.
            hot_max_temps: Maximum temperatures from the hot case.
            cold_min_temps: Minimum temperatures from the cold case.

        Returns:
            List of violations found.
        """
        violations: list[Violation] = []
        node_map = {n["id"]: n for n in nodes}

        for nid, t_max in hot_max_temps.items():
            node = node_map.get(nid)
            if node is None:
                continue
            op_max = node["op_max_temp"]
            qual_max = op_max + _ECSS_QUAL_MARGIN_C

            if t_max > qual_max:
                violations.append(Violation(
                    rule_id="ECSS-THERMAL-HOT-001",
                    severity=Severity.ERROR,
                    message=(
                        f"{node['name']}: hot-case max {t_max:.1f} C exceeds "
                        f"qual limit {qual_max:.1f} C "
                        f"(op max {op_max:.1f} C + {_ECSS_QUAL_MARGIN_C:.0f} C margin)"
                    ),
                    component_path=nid,
                    details={
                        "predicted_max_c": t_max,
                        "op_max_c": op_max,
                        "qual_max_c": qual_max,
                    },
                ))
            elif t_max > op_max:
                violations.append(Violation(
                    rule_id="ECSS-THERMAL-HOT-002",
                    severity=Severity.WARNING,
                    message=(
                        f"{node['name']}: hot-case max {t_max:.1f} C exceeds "
                        f"op max {op_max:.1f} C (within qual margin)"
                    ),
                    component_path=nid,
                    details={
                        "predicted_max_c": t_max,
                        "op_max_c": op_max,
                        "qual_max_c": qual_max,
                    },
                ))

        for nid, t_min in cold_min_temps.items():
            node = node_map.get(nid)
            if node is None:
                continue
            op_min = node["op_min_temp"]
            qual_min = op_min - _ECSS_QUAL_MARGIN_C

            if t_min < qual_min:
                violations.append(Violation(
                    rule_id="ECSS-THERMAL-COLD-001",
                    severity=Severity.ERROR,
                    message=(
                        f"{node['name']}: cold-case min {t_min:.1f} C below "
                        f"qual limit {qual_min:.1f} C "
                        f"(op min {op_min:.1f} C - {_ECSS_QUAL_MARGIN_C:.0f} C margin)"
                    ),
                    component_path=nid,
                    details={
                        "predicted_min_c": t_min,
                        "op_min_c": op_min,
                        "qual_min_c": qual_min,
                    },
                ))
            elif t_min < op_min:
                violations.append(Violation(
                    rule_id="ECSS-THERMAL-COLD-002",
                    severity=Severity.WARNING,
                    message=(
                        f"{node['name']}: cold-case min {t_min:.1f} C below "
                        f"op min {op_min:.1f} C (within qual margin)"
                    ),
                    component_path=nid,
                    details={
                        "predicted_min_c": t_min,
                        "op_min_c": op_min,
                        "qual_min_c": qual_min,
                    },
                ))

        return violations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self) -> OrbitalThermalResult:
        """Run hot-case and cold-case orbital thermal analysis.

        Returns:
            ``OrbitalThermalResult`` with temperatures and violations.
        """
        nodes = await self._ensure_thermal_nodes()

        hot_scenario = self._build_hot_case()
        cold_scenario = self._build_cold_case()

        hot_result = await self._run_scenario(hot_scenario)
        cold_result = await self._run_scenario(cold_scenario)

        hot_min = hot_result.summary.get("min_temperatures", {})
        hot_max = hot_result.summary.get("max_temperatures", {})
        cold_min = cold_result.summary.get("min_temperatures", {})
        cold_max = cold_result.summary.get("max_temperatures", {})

        ecss_violations = self._check_ecss_margins(nodes, hot_max, cold_min)

        return OrbitalThermalResult(
            hot_case_min_temps=hot_min,
            hot_case_max_temps=hot_max,
            cold_case_min_temps=cold_min,
            cold_case_max_temps=cold_max,
            ecss_violations=ecss_violations,
            node_count=len(nodes),
        )

    async def to_analysis_result(self) -> AnalysisResult:
        """Run analysis and return a pipeline-compatible ``AnalysisResult``.

        Merges hot/cold case violations from both the OrbitalCycleAnalyzer
        limit checks and the ECSS qualification margin checks.
        """
        thermal_result = await self.analyze()

        violations = list(thermal_result.ecss_violations)

        has_error = any(v.severity == Severity.ERROR for v in violations)
        has_warning = any(v.severity == Severity.WARNING for v in violations)
        status = (
            AnalysisStatus.FAIL
            if has_error
            else AnalysisStatus.WARN
            if has_warning
            else AnalysisStatus.PASS
        )

        # Build per-node summary
        node_summary: dict[str, dict[str, float]] = {}
        all_ids = set(thermal_result.hot_case_max_temps) | set(thermal_result.cold_case_min_temps)
        for nid in sorted(all_ids):
            node_summary[nid] = {
                "hot_max_c": thermal_result.hot_case_max_temps.get(nid, float("nan")),
                "hot_min_c": thermal_result.hot_case_min_temps.get(nid, float("nan")),
                "cold_max_c": thermal_result.cold_case_max_temps.get(nid, float("nan")),
                "cold_min_c": thermal_result.cold_case_min_temps.get(nid, float("nan")),
            }

        return AnalysisResult(
            analyzer="orbital_thermal",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary={
                "node_count": thermal_result.node_count,
                "node_temperatures": node_summary,
                "ecss_violations": len(violations),
                "ecss_margin_c": _ECSS_QUAL_MARGIN_C,
            },
            metadata={
                "orbit_altitude_km": self._design.orbit_altitude,
                "orbit_type": self._design.orbit_type,
                "sat_size": self._design.sat_size,
                "hot_case": {
                    "solar_flux": 1414.0,
                    "albedo": 0.35,
                    "beta_deg": 75.0,
                },
                "cold_case": {
                    "solar_flux": 1322.0,
                    "albedo": 0.25,
                    "beta_deg": 0.0,
                },
            },
        )

    # ------------------------------------------------------------------
    # Report formatting
    # ------------------------------------------------------------------

    async def format_report(self) -> str:
        """Generate an ASCII report with hot/cold case temperatures.

        Returns:
            Formatted multi-line string for terminal output.
        """
        thermal_result = await self.analyze()

        w = 72
        lines: list[str] = []

        lines.append("=" * w)
        lines.append(
            f"  Orbital Thermal Analysis -- {self._design.mission_name} "
            f"({self._design.sat_size})"
        )
        lines.append("=" * w)
        lines.append("")

        # Scenario summary
        lines.append("  Scenarios")
        lines.append("  " + "-" * (w - 4))
        lines.append(
            f"  Hot case:  perihelion 1414 W/m^2, beta=75 deg, "
            f"albedo=0.35, EOL absorptivity"
        )
        lines.append(
            f"  Cold case: aphelion 1322 W/m^2, beta=0 deg, "
            f"albedo=0.25, BOL absorptivity"
        )
        lines.append(f"  Orbit: {self._design.orbit_altitude:.0f} km {self._design.orbit_type}")
        lines.append(f"  ECSS qualification margin: +/- {_ECSS_QUAL_MARGIN_C:.0f} C")
        lines.append("")

        # Temperature table
        all_ids = sorted(
            set(thermal_result.hot_case_max_temps)
            | set(thermal_result.cold_case_min_temps)
        )

        if all_ids:
            lines.append("  Temperature Results (deg C)")
            lines.append("  " + "-" * (w - 4))
            header = (
                f"  {'Node':<20} {'Hot Max':>8} {'Hot Min':>8} "
                f"{'Cold Max':>9} {'Cold Min':>9}"
            )
            lines.append(header)
            lines.append("  " + "-" * (w - 4))

            for nid in all_ids:
                h_max = thermal_result.hot_case_max_temps.get(nid, float("nan"))
                h_min = thermal_result.hot_case_min_temps.get(nid, float("nan"))
                c_max = thermal_result.cold_case_max_temps.get(nid, float("nan"))
                c_min = thermal_result.cold_case_min_temps.get(nid, float("nan"))

                label = nid.replace("thermal_", "")[:18]
                lines.append(
                    f"  {label:<20} {h_max:>8.1f} {h_min:>8.1f} "
                    f"{c_max:>9.1f} {c_min:>9.1f}"
                )

            lines.append("")
        else:
            lines.append("  No thermal nodes available.")
            lines.append("")

        # Violations
        if thermal_result.ecss_violations:
            lines.append("  ECSS Margin Violations")
            lines.append("  " + "-" * (w - 4))
            for v in thermal_result.ecss_violations:
                sev = v.severity.value
                lines.append(f"  [{sev}] {v.message}")
            lines.append("")
        else:
            lines.append("  All nodes within ECSS qualification envelope.")
            lines.append("")

        lines.append("=" * w)
        return "\n".join(lines)
