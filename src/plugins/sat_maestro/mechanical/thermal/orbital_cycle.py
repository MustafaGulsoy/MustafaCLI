"""Orbital thermal cycle analyzer using Euler time-stepping."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np

from ...core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)

# Default LEO orbit parameters
_DEFAULT_ORBIT_PERIOD = 5400.0  # seconds (~90 min)
_DEFAULT_ECLIPSE_FRACTION = 0.35
_DEFAULT_SOLAR_FLUX = 1361.0  # W/m^2 (solar constant at 1 AU)
_DEFAULT_ALBEDO = 0.3
_DEFAULT_ABSORPTIVITY = 0.5  # solar absorptivity
_DEFAULT_AREA = 0.01  # m^2 (effective area per node for solar input)

# Simulation parameters
_TIME_STEP = 10.0  # seconds
_NUM_ORBITS = 3  # simulate multiple orbits to reach quasi-steady state

# Small radiation to space
_SPACE_TEMP = -270.0  # deg C (approximate deep space)
_SPACE_CONDUCTANCE = 1e-4  # W/K (radiation to space per node)


class OrbitalCycleAnalyzer:
    """Orbital thermal cycle analysis with hot/cold case evaluation.

    Models an orbit as sunlit + eclipse phases. Uses Euler method
    to time-step through the thermal network over multiple orbits.
    Compares resulting min/max temperatures against node limits.
    """

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    async def _fetch_nodes(self) -> list[dict[str, Any]]:
        records = await self._bridge.neo4j_query(
            "MATCH (n:ThermalNode) RETURN n"
        )
        return [r["n"] for r in records]

    async def _fetch_conductances(self) -> list[dict[str, Any]]:
        records = await self._bridge.neo4j_query(
            "MATCH (c:ThermalConductance) RETURN c"
        )
        return [r["c"] for r in records]

    async def analyze(
        self,
        orbit_period: float = _DEFAULT_ORBIT_PERIOD,
        eclipse_fraction: float = _DEFAULT_ECLIPSE_FRACTION,
        solar_flux: float = _DEFAULT_SOLAR_FLUX,
        albedo: float = _DEFAULT_ALBEDO,
        absorptivity: float = _DEFAULT_ABSORPTIVITY,
        area: float = _DEFAULT_AREA,
    ) -> AnalysisResult:
        """Run orbital thermal cycle analysis.

        Args:
            orbit_period: Orbit period in seconds.
            eclipse_fraction: Fraction of orbit in eclipse (0-1).
            solar_flux: Solar flux at spacecraft distance (W/m^2).
            albedo: Earth albedo factor.
            absorptivity: Solar absorptivity of nodes.
            area: Effective area per node for solar heating (m^2).
        """
        raw_nodes = await self._fetch_nodes()
        raw_conductances = await self._fetch_conductances()

        if not raw_nodes:
            return AnalysisResult(
                analyzer="orbital_cycle",
                status=AnalysisStatus.PASS,
                timestamp=datetime.now(),
                summary={"min_temperatures": {}, "max_temperatures": {}},
                metadata={"orbit_period": orbit_period},
            )

        n = len(raw_nodes)
        node_ids = [node["id"] for node in raw_nodes]
        id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        # Initial temperatures
        T = np.array([node["temperature"] for node in raw_nodes], dtype=float)
        capacities = np.array([node.get("capacity", 100.0) for node in raw_nodes], dtype=float)
        # Ensure minimum capacity to avoid division by zero
        capacities = np.maximum(capacities, 1.0)
        powers = np.array([node.get("power_dissipation", 0.0) for node in raw_nodes], dtype=float)

        # Build conductance adjacency
        G_matrix = np.zeros((n, n))
        for cond in raw_conductances:
            a_id = cond["node_a_id"]
            b_id = cond["node_b_id"]
            val = cond.get("value", 0.0)
            if a_id in id_to_idx and b_id in id_to_idx:
                i, j = id_to_idx[a_id], id_to_idx[b_id]
                G_matrix[i, j] += val
                G_matrix[j, i] += val

        # Solar heat input per node (simplified: uniform for all nodes)
        q_solar = absorptivity * solar_flux * area
        q_albedo = absorptivity * albedo * solar_flux * area * 0.3  # reduced albedo contribution

        # Eclipse timing
        sunlit_duration = orbit_period * (1.0 - eclipse_fraction)
        eclipse_start = sunlit_duration
        total_time = orbit_period * _NUM_ORBITS
        dt = _TIME_STEP

        # Track min/max over last orbit
        steps = int(total_time / dt)
        last_orbit_start = orbit_period * (_NUM_ORBITS - 1)

        T_min = np.full(n, np.inf)
        T_max = np.full(n, -np.inf)

        for step in range(steps):
            t = step * dt
            orbit_time = t % orbit_period
            in_sunlight = orbit_time < sunlit_duration

            # Heat input
            Q = powers.copy()
            if in_sunlight:
                Q += q_solar + q_albedo

            # Conduction between nodes
            dT = np.zeros(n)
            for i in range(n):
                for j in range(n):
                    if G_matrix[i, j] > 0:
                        dT[i] += G_matrix[i, j] * (T[j] - T[i])

            # Radiation to space (simplified linear)
            dT += _SPACE_CONDUCTANCE * (_SPACE_TEMP - T)

            # Euler step: C * dT/dt = Q + conduction + radiation
            T = T + dt * (Q + dT) / capacities

            # Track min/max in the last orbit
            if t >= last_orbit_start:
                T_min = np.minimum(T_min, T)
                T_max = np.maximum(T_max, T)

        # Build results
        min_temps = {nid: float(T_min[i]) for i, nid in enumerate(node_ids)}
        max_temps = {nid: float(T_max[i]) for i, nid in enumerate(node_ids)}

        # Check against limits
        violations: list[Violation] = []
        for node in raw_nodes:
            nid = node["id"]
            name = node["name"]
            t_min_limit = node["op_min_temp"]
            t_max_limit = node["op_max_temp"]

            if max_temps[nid] > t_max_limit:
                violations.append(Violation(
                    rule_id="ORBITAL-HOT-CASE",
                    severity=Severity.ERROR,
                    message=(
                        f"{name}: hot case {max_temps[nid]:.1f} deg C "
                        f"exceeds max {t_max_limit:.1f} deg C"
                    ),
                    component_path=nid,
                    details={
                        "max_temperature": max_temps[nid],
                        "op_max_temp": t_max_limit,
                    },
                ))

            if min_temps[nid] < t_min_limit:
                violations.append(Violation(
                    rule_id="ORBITAL-COLD-CASE",
                    severity=Severity.ERROR,
                    message=(
                        f"{name}: cold case {min_temps[nid]:.1f} deg C "
                        f"below min {t_min_limit:.1f} deg C"
                    ),
                    component_path=nid,
                    details={
                        "min_temperature": min_temps[nid],
                        "op_min_temp": t_min_limit,
                    },
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
            analyzer="orbital_cycle",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary={
                "min_temperatures": min_temps,
                "max_temperatures": max_temps,
                "node_count": n,
            },
            metadata={
                "orbit_period": orbit_period,
                "eclipse_fraction": eclipse_fraction,
                "solar_flux": solar_flux,
                "albedo": albedo,
                "num_orbits_simulated": _NUM_ORBITS,
                "time_step": _TIME_STEP,
            },
        )
