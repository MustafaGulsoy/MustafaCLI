"""Tests for Kinematic + Kinetic Analyzer."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.graph_models import (
    AnalysisStatus,
    Severity,
)
from src.plugins.sat_maestro.mechanical.mechanism.kinematic import KinematicAnalyzer


@pytest.fixture
def mock_bridge() -> McpBridge:
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock(return_value=[])
    return bridge


@pytest.fixture
def analyzer(mock_bridge: McpBridge) -> KinematicAnalyzer:
    return KinematicAnalyzer(mock_bridge)


def _make_mech_joint(
    mech_id: str = "m1",
    mech_name: str = "Hinge A",
    mech_type: str = "HINGE",
    joint_id: str = "j1",
    joint_type: str = "REVOLUTE",
    available_torque: float = 10.0,
    friction_torque: float = 1.0,
    gravity_torque: float = 0.5,
    spring_torque: float = 0.3,
    target_angle: float = 90.0,
    inertia: float = 0.1,
    required_cycles: int = 100,
    qualified_cycles: int = 500,
) -> tuple[list[dict], list[dict]]:
    """Helper to build mock mechanism + joint data."""
    mechs = [{"m": {
        "id": mech_id, "name": mech_name, "type": mech_type,
        "state": "stowed", "dof": 1, "sequence_order": 1,
        "required_cycles": required_cycles, "qualified_cycles": qualified_cycles,
    }}]
    joints = [{"j": {
        "id": joint_id, "type": joint_type,
        "min_angle": 0, "max_angle": 180,
        "torque": available_torque,
        "friction_torque": friction_torque,
        "gravity_torque": gravity_torque,
        "spring_torque": spring_torque,
        "inertia": inertia,
        "structure_a_id": "s1", "structure_b_id": "s2",
    }, "mech_id": mech_id, "target_angle": target_angle}]
    return mechs, joints


class TestTorqueMargin:
    """Torque margin = (available - required) / required. ECSS requires >= 2.0 (200%)."""

    @pytest.mark.asyncio
    async def test_sufficient_torque_margin_passes(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        # required = 1.0 + 0.5 + 0.3 = 1.8, margin = (10 - 1.8)/1.8 = 4.55 > 2.0
        mechs, joints = _make_mech_joint(available_torque=10.0, friction_torque=1.0,
                                          gravity_torque=0.5, spring_torque=0.3)
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        torque_violations = [v for v in result.violations if "torque margin" in v.message.lower()]
        assert len(torque_violations) == 0

    @pytest.mark.asyncio
    async def test_insufficient_torque_margin_fails(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        # required = 3.0 + 1.0 + 0.5 = 4.5, margin = (8 - 4.5)/4.5 = 0.78 < 2.0
        mechs, joints = _make_mech_joint(available_torque=8.0, friction_torque=3.0,
                                          gravity_torque=1.0, spring_torque=0.5)
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.FAIL
        torque_violations = [v for v in result.violations if "torque margin" in v.message.lower()]
        assert len(torque_violations) == 1
        assert torque_violations[0].severity == Severity.ERROR

    @pytest.mark.asyncio
    async def test_exact_boundary_torque_margin_passes(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        # required = 1.0, available = 3.0, margin = (3-1)/1 = 2.0 exactly
        mechs, joints = _make_mech_joint(available_torque=3.0, friction_torque=0.5,
                                          gravity_torque=0.3, spring_torque=0.2)
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        torque_violations = [v for v in result.violations if "torque margin" in v.message.lower()]
        assert len(torque_violations) == 0

    @pytest.mark.asyncio
    async def test_torque_margin_in_summary(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        mechs, joints = _make_mech_joint(available_torque=10.0, friction_torque=1.0,
                                          gravity_torque=0.5, spring_torque=0.3)
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        assert "torque_margins" in result.summary
        assert len(result.summary["torque_margins"]) == 1


class TestFrictionAnalysis:
    """Friction torque must be less than available torque."""

    @pytest.mark.asyncio
    async def test_friction_within_limit(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        mechs, joints = _make_mech_joint(available_torque=10.0, friction_torque=2.0)
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        friction_violations = [v for v in result.violations if "friction" in v.message.lower()]
        assert len(friction_violations) == 0

    @pytest.mark.asyncio
    async def test_friction_exceeds_available_torque(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        mechs, joints = _make_mech_joint(available_torque=5.0, friction_torque=6.0)
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.FAIL
        friction_violations = [v for v in result.violations if "friction" in v.message.lower()]
        assert len(friction_violations) == 1
        assert friction_violations[0].severity == Severity.ERROR


class TestDeploymentTime:
    """Deployment time estimation using angular velocity model."""

    @pytest.mark.asyncio
    async def test_deployment_time_calculated(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        # net_torque = 10 - (1+0.5+0.3) = 8.2, angular_accel = 8.2/0.1 = 82 rad/s^2
        # angle = 90 deg = pi/2 rad, time = sqrt(2*angle/accel) = sqrt(2*1.571/82) ~= 0.196s
        mechs, joints = _make_mech_joint(
            available_torque=10.0, friction_torque=1.0, gravity_torque=0.5,
            spring_torque=0.3, target_angle=90.0, inertia=0.1,
        )
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        assert "deployment_times" in result.summary
        times = result.summary["deployment_times"]
        assert len(times) == 1
        assert times[0]["time_s"] > 0

    @pytest.mark.asyncio
    async def test_deployment_time_zero_net_torque_warning(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        # net_torque = 2 - (1+0.5+0.5) = 0 => cannot estimate time
        mechs, joints = _make_mech_joint(
            available_torque=2.0, friction_torque=1.0, gravity_torque=0.5,
            spring_torque=0.5, target_angle=90.0, inertia=0.1,
        )
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        time_warnings = [v for v in result.violations if "deployment time" in v.message.lower()]
        assert len(time_warnings) >= 1


class TestLifeFactor:
    """Mechanism life factor must be >= 4x required cycles."""

    @pytest.mark.asyncio
    async def test_sufficient_life_factor(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        # qualified=500, required=100, factor=5.0 >= 4.0
        mechs, joints = _make_mech_joint(required_cycles=100, qualified_cycles=500)
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        life_violations = [v for v in result.violations if "life" in v.message.lower()]
        assert len(life_violations) == 0

    @pytest.mark.asyncio
    async def test_insufficient_life_factor(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        # qualified=200, required=100, factor=2.0 < 4.0
        mechs, joints = _make_mech_joint(required_cycles=100, qualified_cycles=200)
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.FAIL
        life_violations = [v for v in result.violations if "life" in v.message.lower()]
        assert len(life_violations) == 1
        assert life_violations[0].severity == Severity.ERROR

    @pytest.mark.asyncio
    async def test_missing_cycle_data_skipped(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        """No cycle data => no life violation (data simply missing)."""
        mechs, joints = _make_mech_joint()
        mechs[0]["m"].pop("required_cycles", None)
        mechs[0]["m"].pop("qualified_cycles", None)
        mock_bridge.neo4j_query = AsyncMock(side_effect=[mechs, joints])
        result = await analyzer.analyze()
        life_violations = [v for v in result.violations if "life" in v.message.lower()]
        assert len(life_violations) == 0


class TestEmptyData:
    @pytest.mark.asyncio
    async def test_no_data_returns_pass(self, analyzer: KinematicAnalyzer, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[[], []])
        result = await analyzer.analyze()
        assert result.status == AnalysisStatus.PASS
        assert result.analyzer == "KinematicAnalyzer"
