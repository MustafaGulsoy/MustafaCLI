"""Lumped-parameter thermal node model solver."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np

from ...core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    ThermalConductance,
    ThermalNode,
    Violation,
)
from ...core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)

# Small conductance to space (boundary) to avoid singular matrix
_BOUNDARY_CONDUCTANCE = 1e-6  # W/K
_REFERENCE_TEMP = 0.0  # deg C (space reference)


class ThermalNodeModel:
    """Lumped-parameter thermal solver using conductance matrix approach.

    Builds [G]{T} = {Q} from ThermalNode / ThermalConductance graph
    and solves for steady-state temperatures using numpy.
    """

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    async def _fetch_nodes(self) -> list[dict[str, Any]]:
        """Query all ThermalNode from Neo4j."""
        records = await self._bridge.neo4j_query(
            "MATCH (n:ThermalNode) RETURN n"
        )
        return [r["n"] for r in records]

    async def _fetch_conductances(self) -> list[dict[str, Any]]:
        """Query all ThermalConductance from Neo4j."""
        records = await self._bridge.neo4j_query(
            "MATCH (c:ThermalConductance) RETURN c"
        )
        return [r["c"] for r in records]

    def _build_system(
        self,
        nodes: list[dict[str, Any]],
        conductances: list[dict[str, Any]],
    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """Build conductance matrix [G] and heat load vector {Q}.

        Returns (G, Q, node_ids) where G is NxN and Q is Nx1.
        Each node gets a small boundary conductance to a reference
        temperature to ensure the system is non-singular.
        """
        n = len(nodes)
        node_ids = [node["id"] for node in nodes]
        id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        G = np.zeros((n, n))
        Q = np.zeros(n)

        # Fill heat load vector from power dissipation
        for i, node in enumerate(nodes):
            Q[i] = node.get("power_dissipation", 0.0)

        # Add boundary conductance to space for every node
        for i in range(n):
            G[i, i] += _BOUNDARY_CONDUCTANCE
            Q[i] += _BOUNDARY_CONDUCTANCE * _REFERENCE_TEMP

        # Fill conductance matrix from links
        for cond in conductances:
            a_id = cond["node_a_id"]
            b_id = cond["node_b_id"]
            value = cond.get("value", 0.0)

            if a_id not in id_to_idx or b_id not in id_to_idx:
                logger.warning(
                    "Conductance %s references unknown node(s): %s, %s",
                    cond.get("id", "?"), a_id, b_id,
                )
                continue

            i = id_to_idx[a_id]
            j = id_to_idx[b_id]

            G[i, i] += value
            G[j, j] += value
            G[i, j] -= value
            G[j, i] -= value

        return G, Q, node_ids

    async def analyze(self) -> AnalysisResult:
        """Run steady-state thermal analysis.

        Solves [G]{T} = {Q} and returns temperatures per node.
        """
        raw_nodes = await self._fetch_nodes()
        raw_conductances = await self._fetch_conductances()

        if not raw_nodes:
            return AnalysisResult(
                analyzer="thermal_node_model",
                status=AnalysisStatus.PASS,
                timestamp=datetime.now(),
                summary={"temperatures": {}, "node_count": 0},
            )

        G, Q, node_ids = self._build_system(raw_nodes, raw_conductances)

        # Solve [G]{T} = {Q}
        try:
            T = np.linalg.solve(G, Q)
        except np.linalg.LinAlgError:
            return AnalysisResult(
                analyzer="thermal_node_model",
                status=AnalysisStatus.FAIL,
                timestamp=datetime.now(),
                violations=[Violation(
                    rule_id="THERMAL-SINGULAR",
                    severity=Severity.ERROR,
                    message="Conductance matrix is singular; check thermal network connectivity.",
                    component_path="thermal_model",
                )],
                summary={"temperatures": {}, "node_count": len(raw_nodes)},
            )

        temperatures = {nid: float(T[i]) for i, nid in enumerate(node_ids)}

        # Write solved temperatures back to Neo4j
        for nid, temp in temperatures.items():
            await self._bridge.neo4j_write(
                "MATCH (n:ThermalNode {id: $id}) SET n.temperature = $temp",
                {"id": nid, "temp": temp},
            )

        return AnalysisResult(
            analyzer="thermal_node_model",
            status=AnalysisStatus.PASS,
            timestamp=datetime.now(),
            summary={
                "temperatures": temperatures,
                "node_count": len(raw_nodes),
                "conductance_count": len(raw_conductances),
                "max_temp": max(temperatures.values()),
                "min_temp": min(temperatures.values()),
            },
            metadata={
                "solver": "numpy.linalg.solve",
                "boundary_conductance": _BOUNDARY_CONDUCTANCE,
                "reference_temp": _REFERENCE_TEMP,
            },
        )
