"""Tests for Deployment Sequence Validator."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
from src.plugins.sat_maestro.core.graph_models import (
    AnalysisStatus,
    Severity,
)
from src.plugins.sat_maestro.mechanical.mechanism.deployment import DeploymentValidator


@pytest.fixture
def mock_bridge() -> McpBridge:
    bridge = McpBridge(servers={})
    bridge.neo4j_query = AsyncMock(return_value=[])
    return bridge


@pytest.fixture
def validator(mock_bridge: McpBridge) -> DeploymentValidator:
    return DeploymentValidator(mock_bridge)


class TestDeploymentSequenceOrder:
    """Mechanisms must deploy in correct sequence_order."""

    @pytest.mark.asyncio
    async def test_valid_sequence_passes(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        """Sequential deployment order 1->2->3 is valid."""
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            # First call: mechanisms
            [
                {"m": {"id": "m1", "name": "Hinge A", "type": "HINGE", "state": "stowed",
                        "dof": 1, "sequence_order": 1}},
                {"m": {"id": "m2", "name": "Latch B", "type": "LATCH", "state": "stowed",
                        "dof": 1, "sequence_order": 2, "latch_state": "locked"}},
                {"m": {"id": "m3", "name": "Hinge C", "type": "HINGE", "state": "stowed",
                        "dof": 1, "sequence_order": 3}},
            ],
            # Second call: joints
            [
                {"j": {"id": "j1", "type": "REVOLUTE", "min_angle": 0, "max_angle": 180,
                        "torque": 10.0, "friction_torque": 1.0,
                        "structure_a_id": "s1", "structure_b_id": "s2"},
                 "mech_id": "m1", "target_angle": 90.0},
                {"j": {"id": "j2", "type": "FIXED", "min_angle": 0, "max_angle": 0,
                        "torque": 5.0, "friction_torque": 0.5,
                        "structure_a_id": "s2", "structure_b_id": "s3"},
                 "mech_id": "m2", "target_angle": 0.0},
                {"j": {"id": "j3", "type": "REVOLUTE", "min_angle": 0, "max_angle": 180,
                        "torque": 10.0, "friction_torque": 1.0,
                        "structure_a_id": "s3", "structure_b_id": "s4"},
                 "mech_id": "m3", "target_angle": 120.0},
            ],
        ])
        result = await validator.validate()
        assert result.status == AnalysisStatus.PASS
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_duplicate_sequence_order_violation(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        """Two mechanisms with the same sequence_order is a violation."""
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [
                {"m": {"id": "m1", "name": "Hinge A", "type": "HINGE", "state": "stowed",
                        "dof": 1, "sequence_order": 1}},
                {"m": {"id": "m2", "name": "Hinge B", "type": "HINGE", "state": "stowed",
                        "dof": 1, "sequence_order": 1}},
            ],
            [
                {"j": {"id": "j1", "type": "REVOLUTE", "min_angle": 0, "max_angle": 180,
                        "torque": 10.0, "friction_torque": 1.0,
                        "structure_a_id": "s1", "structure_b_id": "s2"},
                 "mech_id": "m1", "target_angle": 90.0},
                {"j": {"id": "j2", "type": "REVOLUTE", "min_angle": 0, "max_angle": 180,
                        "torque": 10.0, "friction_torque": 1.0,
                        "structure_a_id": "s2", "structure_b_id": "s3"},
                 "mech_id": "m2", "target_angle": 90.0},
            ],
        ])
        result = await validator.validate()
        assert result.status == AnalysisStatus.FAIL
        seq_violations = [v for v in result.violations if "sequence" in v.message.lower()]
        assert len(seq_violations) >= 1

    @pytest.mark.asyncio
    async def test_gap_in_sequence_is_warning(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        """Non-contiguous sequence (1, 3) issues a warning."""
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [
                {"m": {"id": "m1", "name": "Hinge A", "type": "HINGE", "state": "stowed",
                        "dof": 1, "sequence_order": 1}},
                {"m": {"id": "m2", "name": "Hinge B", "type": "HINGE", "state": "stowed",
                        "dof": 1, "sequence_order": 3}},
            ],
            [
                {"j": {"id": "j1", "type": "REVOLUTE", "min_angle": 0, "max_angle": 180,
                        "torque": 10.0, "friction_torque": 1.0,
                        "structure_a_id": "s1", "structure_b_id": "s2"},
                 "mech_id": "m1", "target_angle": 90.0},
                {"j": {"id": "j2", "type": "REVOLUTE", "min_angle": 0, "max_angle": 180,
                        "torque": 10.0, "friction_torque": 1.0,
                        "structure_a_id": "s2", "structure_b_id": "s3"},
                 "mech_id": "m2", "target_angle": 90.0},
            ],
        ])
        result = await validator.validate()
        gap_warnings = [v for v in result.violations if "gap" in v.message.lower()]
        assert len(gap_warnings) >= 1
        assert gap_warnings[0].severity == Severity.WARNING


class TestAngularLimits:
    """Joint target angles must be within [min_angle, max_angle]."""

    @pytest.mark.asyncio
    async def test_angle_within_limits_passes(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{"m": {"id": "m1", "name": "Hinge A", "type": "HINGE", "state": "stowed",
                    "dof": 1, "sequence_order": 1}}],
            [{"j": {"id": "j1", "type": "REVOLUTE", "min_angle": 0, "max_angle": 180,
                    "torque": 10.0, "friction_torque": 1.0,
                    "structure_a_id": "s1", "structure_b_id": "s2"},
              "mech_id": "m1", "target_angle": 90.0}],
        ])
        result = await validator.validate()
        angle_violations = [v for v in result.violations if "angle" in v.message.lower()]
        assert len(angle_violations) == 0

    @pytest.mark.asyncio
    async def test_angle_exceeds_max_fails(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{"m": {"id": "m1", "name": "Hinge A", "type": "HINGE", "state": "stowed",
                    "dof": 1, "sequence_order": 1}}],
            [{"j": {"id": "j1", "type": "REVOLUTE", "min_angle": 0, "max_angle": 90,
                    "torque": 10.0, "friction_torque": 1.0,
                    "structure_a_id": "s1", "structure_b_id": "s2"},
              "mech_id": "m1", "target_angle": 120.0}],
        ])
        result = await validator.validate()
        assert result.status == AnalysisStatus.FAIL
        angle_violations = [v for v in result.violations if "angle" in v.message.lower()]
        assert len(angle_violations) == 1
        assert angle_violations[0].severity == Severity.ERROR

    @pytest.mark.asyncio
    async def test_angle_below_min_fails(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{"m": {"id": "m1", "name": "Hinge A", "type": "HINGE", "state": "stowed",
                    "dof": 1, "sequence_order": 1}}],
            [{"j": {"id": "j1", "type": "REVOLUTE", "min_angle": 10, "max_angle": 180,
                    "torque": 10.0, "friction_torque": 1.0,
                    "structure_a_id": "s1", "structure_b_id": "s2"},
              "mech_id": "m1", "target_angle": 5.0}],
        ])
        result = await validator.validate()
        assert result.status == AnalysisStatus.FAIL


class TestLatchValidation:
    """Latches must reach locked state after deployment."""

    @pytest.mark.asyncio
    async def test_latch_locked_passes(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{"m": {"id": "m1", "name": "Latch A", "type": "LATCH", "state": "stowed",
                    "dof": 1, "sequence_order": 1, "latch_state": "locked"}}],
            [{"j": {"id": "j1", "type": "FIXED", "min_angle": 0, "max_angle": 0,
                    "torque": 5.0, "friction_torque": 0.5,
                    "structure_a_id": "s1", "structure_b_id": "s2"},
              "mech_id": "m1", "target_angle": 0.0}],
        ])
        result = await validator.validate()
        latch_violations = [v for v in result.violations if "latch" in v.message.lower()]
        assert len(latch_violations) == 0

    @pytest.mark.asyncio
    async def test_latch_unlocked_fails(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{"m": {"id": "m1", "name": "Latch A", "type": "LATCH", "state": "stowed",
                    "dof": 1, "sequence_order": 1, "latch_state": "unlocked"}}],
            [{"j": {"id": "j1", "type": "FIXED", "min_angle": 0, "max_angle": 0,
                    "torque": 5.0, "friction_torque": 0.5,
                    "structure_a_id": "s1", "structure_b_id": "s2"},
              "mech_id": "m1", "target_angle": 0.0}],
        ])
        result = await validator.validate()
        assert result.status == AnalysisStatus.FAIL
        latch_violations = [v for v in result.violations if "latch" in v.message.lower()]
        assert len(latch_violations) == 1
        assert latch_violations[0].severity == Severity.ERROR

    @pytest.mark.asyncio
    async def test_latch_missing_state_warning(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        """Latch mechanism without latch_state property gets a warning."""
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{"m": {"id": "m1", "name": "Latch A", "type": "LATCH", "state": "stowed",
                    "dof": 1, "sequence_order": 1}}],
            [{"j": {"id": "j1", "type": "FIXED", "min_angle": 0, "max_angle": 0,
                    "torque": 5.0, "friction_torque": 0.5,
                    "structure_a_id": "s1", "structure_b_id": "s2"},
              "mech_id": "m1", "target_angle": 0.0}],
        ])
        result = await validator.validate()
        latch_violations = [v for v in result.violations if "latch" in v.message.lower()]
        assert len(latch_violations) >= 1
        assert latch_violations[0].severity == Severity.WARNING


class TestEmptyData:
    """Edge cases with no mechanisms or joints."""

    @pytest.mark.asyncio
    async def test_no_mechanisms_returns_pass(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[[], []])
        result = await validator.validate()
        assert result.status == AnalysisStatus.PASS
        assert result.analyzer == "DeploymentValidator"

    @pytest.mark.asyncio
    async def test_mechanism_without_joints_warning(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [{"m": {"id": "m1", "name": "Hinge A", "type": "HINGE", "state": "stowed",
                    "dof": 1, "sequence_order": 1}}],
            [],  # no joints
        ])
        result = await validator.validate()
        warnings = [v for v in result.violations if v.severity == Severity.WARNING]
        assert len(warnings) >= 1


class TestSummary:
    """Validate summary metadata in result."""

    @pytest.mark.asyncio
    async def test_summary_contains_counts(self, validator: DeploymentValidator, mock_bridge: McpBridge):
        mock_bridge.neo4j_query = AsyncMock(side_effect=[
            [
                {"m": {"id": "m1", "name": "Hinge A", "type": "HINGE", "state": "stowed",
                        "dof": 1, "sequence_order": 1}},
            ],
            [
                {"j": {"id": "j1", "type": "REVOLUTE", "min_angle": 0, "max_angle": 180,
                        "torque": 10.0, "friction_torque": 1.0,
                        "structure_a_id": "s1", "structure_b_id": "s2"},
                 "mech_id": "m1", "target_angle": 90.0},
            ],
        ])
        result = await validator.validate()
        assert "mechanism_count" in result.summary
        assert "joint_count" in result.summary
        assert result.summary["mechanism_count"] == 1
        assert result.summary["joint_count"] == 1
