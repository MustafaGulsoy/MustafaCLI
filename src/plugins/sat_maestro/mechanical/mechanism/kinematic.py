"""Kinematic + Kinetic Analyzer per ECSS-E-ST-33C."""
from __future__ import annotations

import logging
import math
from typing import Any

from src.plugins.sat_maestro.core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from src.plugins.sat_maestro.core.mcp_bridge import McpBridge

logger = logging.getLogger(__name__)

# ECSS-E-ST-33C requires torque margin >= 2.0 (200%)
ECSS_TORQUE_MARGIN_MIN = 2.0
# Life factor >= 4x required cycles
ECSS_LIFE_FACTOR_MIN = 4.0

_MECH_QUERY = """
MATCH (m:Mechanism)
RETURN m {.id, .name, .type, .state, .dof, .sequence_order,
          .required_cycles, .qualified_cycles}
ORDER BY m.sequence_order
"""

_JOINT_QUERY = """
MATCH (m:Mechanism)-[:HAS_JOINT]->(j:Joint)
RETURN j {.id, .type, .min_angle, .max_angle, .torque, .friction_torque,
          .gravity_torque, .spring_torque, .inertia,
          .structure_a_id, .structure_b_id},
       m.id AS mech_id,
       j.target_angle AS target_angle
"""


class KinematicAnalyzer:
    """Kinematic and kinetic analysis of satellite mechanisms.

    Checks per ECSS-E-ST-33C:
    - Torque margin >= 200%
    - Friction torque < available torque
    - Deployment time estimation
    - Mechanism life factor >= 4x
    """

    def __init__(self, bridge: McpBridge) -> None:
        self._bridge = bridge

    async def analyze(self) -> AnalysisResult:
        """Run kinematic/kinetic analysis."""
        mechanisms = await self._bridge.neo4j_query(_MECH_QUERY)
        joints = await self._bridge.neo4j_query(_JOINT_QUERY)

        violations: list[Violation] = []
        torque_margins: list[dict[str, Any]] = []
        deployment_times: list[dict[str, Any]] = []

        # Build joint lookup by mechanism
        joints_by_mech: dict[str, list[dict]] = {}
        for jdata in joints:
            mid = jdata["mech_id"]
            joints_by_mech.setdefault(mid, []).append(jdata)

        for mdata in mechanisms:
            m = mdata["m"]
            mech_joints = joints_by_mech.get(m["id"], [])

            for jdata in mech_joints:
                j = jdata["j"]
                joint_id = j["id"]

                friction = j.get("friction_torque", 0.0)
                gravity = j.get("gravity_torque", 0.0)
                spring = j.get("spring_torque", 0.0)
                available = j.get("torque", 0.0)
                required = friction + gravity + spring

                # Torque margin analysis
                margin_info = self._torque_margin(joint_id, available, required)
                torque_margins.append(margin_info)
                if margin_info.get("violation"):
                    violations.append(margin_info["violation"])

                # Friction analysis
                fv = self._friction_check(joint_id, available, friction)
                if fv:
                    violations.append(fv)

                # Deployment time estimation
                target_angle = jdata.get("target_angle", 0.0)
                inertia = j.get("inertia", 0.0)
                dt_info = self._deployment_time(joint_id, available, required, target_angle, inertia)
                deployment_times.append(dt_info)
                if dt_info.get("violation"):
                    violations.append(dt_info["violation"])

            # Life factor check
            lv = self._life_factor_check(m)
            if lv:
                violations.append(lv)

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        status = AnalysisStatus.FAIL if has_errors else (
            AnalysisStatus.WARN if violations else AnalysisStatus.PASS
        )

        return AnalysisResult(
            analyzer="KinematicAnalyzer",
            status=status,
            violations=violations,
            summary={
                "mechanism_count": len(mechanisms),
                "joint_count": len(joints),
                "torque_margins": torque_margins,
                "deployment_times": deployment_times,
                "standard": "ECSS-E-ST-33C",
            },
        )

    def _torque_margin(self, joint_id: str, available: float,
                       required: float) -> dict[str, Any]:
        """Calculate torque margin: (available - required) / required."""
        if required <= 0:
            return {"joint_id": joint_id, "margin": float("inf"), "available": available,
                    "required": required}

        margin = (available - required) / required
        info: dict[str, Any] = {
            "joint_id": joint_id, "margin": round(margin, 3),
            "available": available, "required": required,
        }

        if margin < ECSS_TORQUE_MARGIN_MIN:
            info["violation"] = Violation(
                rule_id="ECSS-E-ST-33C-TRQ-001",
                severity=Severity.ERROR,
                message=(f"Joint {joint_id} torque margin {margin:.1%} "
                         f"below ECSS minimum {ECSS_TORQUE_MARGIN_MIN:.0%}"),
                component_path=f"/mechanism/joint/{joint_id}",
                details={"margin": margin, "available": available, "required": required,
                         "min_margin": ECSS_TORQUE_MARGIN_MIN},
            )

        return info

    def _friction_check(self, joint_id: str, available: float,
                        friction: float) -> Violation | None:
        """Check friction torque vs available torque."""
        if friction >= available:
            return Violation(
                rule_id="ECSS-E-ST-33C-FRC-001",
                severity=Severity.ERROR,
                message=(f"Joint {joint_id} friction torque {friction} Nm "
                         f">= available torque {available} Nm"),
                component_path=f"/mechanism/joint/{joint_id}",
                details={"friction_torque": friction, "available_torque": available},
            )
        return None

    def _deployment_time(self, joint_id: str, available: float, required: float,
                         target_angle: float, inertia: float) -> dict[str, Any]:
        """Estimate deployment time using constant-acceleration model.

        angle = 0.5 * alpha * t^2  =>  t = sqrt(2 * angle / alpha)
        where alpha = net_torque / inertia
        """
        net_torque = available - required
        angle_rad = math.radians(abs(target_angle))

        info: dict[str, Any] = {"joint_id": joint_id}

        if net_torque <= 0 or inertia <= 0 or angle_rad <= 0:
            info["time_s"] = None
            if angle_rad > 0:
                info["violation"] = Violation(
                    rule_id="ECSS-E-ST-33C-DPL-001",
                    severity=Severity.WARNING,
                    message=(f"Deployment time cannot be estimated for joint {joint_id}: "
                             f"net torque={net_torque:.2f} Nm, inertia={inertia} kg*m^2"),
                    component_path=f"/mechanism/joint/{joint_id}",
                    details={"net_torque": net_torque, "inertia": inertia},
                )
            return info

        alpha = net_torque / inertia  # angular acceleration (rad/s^2)
        t = math.sqrt(2.0 * angle_rad / alpha)
        info["time_s"] = round(t, 4)
        return info

    def _life_factor_check(self, m: dict[str, Any]) -> Violation | None:
        """Check mechanism life factor >= 4x required cycles."""
        required_cycles = m.get("required_cycles")
        qualified_cycles = m.get("qualified_cycles")

        if required_cycles is None or qualified_cycles is None:
            return None
        if required_cycles <= 0:
            return None

        factor = qualified_cycles / required_cycles
        if factor < ECSS_LIFE_FACTOR_MIN:
            return Violation(
                rule_id="ECSS-E-ST-33C-LIFE-001",
                severity=Severity.ERROR,
                message=(f"Mechanism '{m.get('name', m['id'])}' life factor {factor:.1f}x "
                         f"below ECSS minimum {ECSS_LIFE_FACTOR_MIN:.0f}x"),
                component_path=f"/mechanism/{m['id']}",
                details={"factor": factor, "required_cycles": required_cycles,
                         "qualified_cycles": qualified_cycles,
                         "min_factor": ECSS_LIFE_FACTOR_MIN},
            )
        return None
