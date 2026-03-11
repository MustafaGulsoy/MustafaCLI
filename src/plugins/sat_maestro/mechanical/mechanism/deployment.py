"""Deployment Sequence Validator per ECSS-E-ST-33C."""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from src.plugins.sat_maestro.core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from src.plugins.sat_maestro.core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)

_MECH_QUERY = """
MATCH (m:Mechanism)
RETURN m {.id, .name, .type, .state, .dof, .sequence_order, .latch_state}
ORDER BY m.sequence_order
"""

_JOINT_QUERY = """
MATCH (m:Mechanism)-[:HAS_JOINT]->(j:Joint)
RETURN j {.id, .type, .min_angle, .max_angle, .torque, .friction_torque,
          .structure_a_id, .structure_b_id},
       m.id AS mech_id,
       j.target_angle AS target_angle
"""


class DeploymentValidator:
    """Validates satellite deployment sequences per ECSS-E-ST-33C.

    Checks:
    - Deployment sequence ordering (no duplicates, no gaps)
    - Joint angular limits (target within [min_angle, max_angle])
    - Latch positions (all latches must reach locked state)
    """

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    async def validate(self) -> AnalysisResult:
        """Run all deployment validations and return result."""
        mechanisms = await self._bridge.neo4j_query(_MECH_QUERY)
        joints = await self._bridge.neo4j_query(_JOINT_QUERY)

        violations: list[Violation] = []

        violations.extend(self._check_sequence_order(mechanisms))
        violations.extend(self._check_angular_limits(joints))
        violations.extend(self._check_latch_positions(mechanisms))
        violations.extend(self._check_joints_exist(mechanisms, joints))

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        status = AnalysisStatus.FAIL if has_errors else (
            AnalysisStatus.WARN if violations else AnalysisStatus.PASS
        )

        return AnalysisResult(
            analyzer="DeploymentValidator",
            status=status,
            violations=violations,
            summary={
                "mechanism_count": len(mechanisms),
                "joint_count": len(joints),
                "standard": "ECSS-E-ST-33C",
            },
        )

    def _check_sequence_order(self, mechanisms: list[dict[str, Any]]) -> list[Violation]:
        """Validate deployment sequence ordering."""
        violations: list[Violation] = []
        if not mechanisms:
            return violations

        orders = [m["m"]["sequence_order"] for m in mechanisms]

        # Check for duplicate sequence orders
        counts = Counter(orders)
        for order, count in counts.items():
            if count > 1:
                dupes = [m["m"]["name"] for m in mechanisms if m["m"]["sequence_order"] == order]
                violations.append(Violation(
                    rule_id="ECSS-E-ST-33C-SEQ-001",
                    severity=Severity.ERROR,
                    message=f"Duplicate deployment sequence order {order}: {', '.join(dupes)}",
                    component_path="/deployment/sequence",
                    details={"order": order, "mechanisms": dupes},
                ))

        # Check for gaps in sequence
        sorted_orders = sorted(set(orders))
        if len(sorted_orders) > 1:
            for i in range(1, len(sorted_orders)):
                if sorted_orders[i] - sorted_orders[i - 1] > 1:
                    violations.append(Violation(
                        rule_id="ECSS-E-ST-33C-SEQ-002",
                        severity=Severity.WARNING,
                        message=f"Gap in deployment sequence between order {sorted_orders[i-1]} and {sorted_orders[i]}",
                        component_path="/deployment/sequence",
                        details={"gap_from": sorted_orders[i - 1], "gap_to": sorted_orders[i]},
                    ))

        return violations

    def _check_angular_limits(self, joints: list[dict[str, Any]]) -> list[Violation]:
        """Validate joint target angles within allowed range."""
        violations: list[Violation] = []

        for jdata in joints:
            j = jdata["j"]
            target = jdata.get("target_angle")
            if target is None:
                continue

            min_a = j.get("min_angle", 0.0)
            max_a = j.get("max_angle", 360.0)
            joint_id = j["id"]

            if target > max_a:
                violations.append(Violation(
                    rule_id="ECSS-E-ST-33C-ANG-001",
                    severity=Severity.ERROR,
                    message=f"Joint {joint_id} target angle {target} deg exceeds max {max_a} deg",
                    component_path=f"/deployment/joint/{joint_id}",
                    details={"target": target, "max_angle": max_a, "min_angle": min_a},
                ))
            elif target < min_a:
                violations.append(Violation(
                    rule_id="ECSS-E-ST-33C-ANG-001",
                    severity=Severity.ERROR,
                    message=f"Joint {joint_id} target angle {target} deg below min {min_a} deg",
                    component_path=f"/deployment/joint/{joint_id}",
                    details={"target": target, "max_angle": max_a, "min_angle": min_a},
                ))

        return violations

    def _check_latch_positions(self, mechanisms: list[dict[str, Any]]) -> list[Violation]:
        """Validate that all latch mechanisms reach locked state."""
        violations: list[Violation] = []

        for mdata in mechanisms:
            m = mdata["m"]
            if m.get("type") != "LATCH":
                continue

            latch_state = m.get("latch_state")
            name = m.get("name", m["id"])

            if latch_state is None:
                violations.append(Violation(
                    rule_id="ECSS-E-ST-33C-LATCH-001",
                    severity=Severity.WARNING,
                    message=f"Latch '{name}' has no latch_state defined",
                    component_path=f"/deployment/mechanism/{m['id']}",
                    details={"mechanism_id": m["id"]},
                ))
            elif latch_state != "locked":
                violations.append(Violation(
                    rule_id="ECSS-E-ST-33C-LATCH-002",
                    severity=Severity.ERROR,
                    message=f"Latch '{name}' not in locked state (current: {latch_state})",
                    component_path=f"/deployment/mechanism/{m['id']}",
                    details={"mechanism_id": m["id"], "latch_state": latch_state},
                ))

        return violations

    def _check_joints_exist(self, mechanisms: list[dict[str, Any]],
                            joints: list[dict[str, Any]]) -> list[Violation]:
        """Warn if a mechanism has no associated joints."""
        violations: list[Violation] = []
        if not mechanisms:
            return violations

        mech_ids_with_joints = {j["mech_id"] for j in joints}
        for mdata in mechanisms:
            m = mdata["m"]
            if m["id"] not in mech_ids_with_joints:
                violations.append(Violation(
                    rule_id="ECSS-E-ST-33C-MECH-001",
                    severity=Severity.WARNING,
                    message=f"Mechanism '{m.get('name', m['id'])}' has no associated joints",
                    component_path=f"/deployment/mechanism/{m['id']}",
                    details={"mechanism_id": m["id"]},
                ))

        return violations
