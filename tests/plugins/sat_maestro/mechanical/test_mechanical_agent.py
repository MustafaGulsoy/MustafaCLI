"""Tests for MechanicalAgent orchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.plugins.sat_maestro.mechanical.agent import MechanicalAgent
from src.plugins.sat_maestro.core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation
from src.plugins.sat_maestro.config import SatMaestroConfig


class TestMechanicalAgent:

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def config(self):
        return SatMaestroConfig()

    @pytest.fixture
    def agent(self, mock_bridge, config):
        return MechanicalAgent(mock_bridge, config)

    def test_agent_creates_all_analyzers(self, agent):
        """Agent initializes all sub-analyzers."""
        assert agent.mass_budget is not None
        assert agent.cog is not None
        assert agent.assembly is not None
        assert agent.thermal_solver is not None
        assert agent.thermal_checker is not None
        assert agent.orbital_cycle is not None
        assert agent.deployment is not None
        assert agent.kinematic is not None
        assert agent.modal is not None
        assert agent.random_vib is not None
        assert agent.shock is not None

    @pytest.mark.asyncio
    async def test_run_full_analysis_all_pass(self, agent):
        """Full analysis returns all results when everything passes."""
        pass_result = AnalysisResult(
            analyzer="test", status=AnalysisStatus.PASS,
        )
        with patch.object(agent.mass_budget, 'analyze', return_value=pass_result), \
             patch.object(agent.cog, 'calculate', return_value=pass_result), \
             patch.object(agent.assembly, 'validate', return_value=pass_result), \
             patch.object(agent.thermal_solver, 'analyze', return_value=pass_result), \
             patch.object(agent.thermal_checker, 'analyze', return_value=pass_result), \
             patch.object(agent.orbital_cycle, 'analyze', return_value=pass_result), \
             patch.object(agent.deployment, 'validate', return_value=pass_result), \
             patch.object(agent.kinematic, 'analyze', return_value=pass_result):

            results, summary = await agent.run_full_analysis(mass_budget=100.0)

        assert len(results) == 8
        assert all(r.status == AnalysisStatus.PASS for r in results)
        assert "PASS" in summary

    @pytest.mark.asyncio
    async def test_run_full_analysis_with_failures(self, agent):
        """Full analysis reports overall FAIL if any analyzer fails."""
        pass_result = AnalysisResult(
            analyzer="test", status=AnalysisStatus.PASS,
        )
        fail_result = AnalysisResult(
            analyzer="mass_budget", status=AnalysisStatus.FAIL,
            violations=[Violation(
                rule_id="TEST", severity=Severity.ERROR,
                message="over budget", component_path="spacecraft",
            )],
        )
        with patch.object(agent.mass_budget, 'analyze', return_value=fail_result), \
             patch.object(agent.cog, 'calculate', return_value=pass_result), \
             patch.object(agent.assembly, 'validate', return_value=pass_result), \
             patch.object(agent.thermal_solver, 'analyze', return_value=pass_result), \
             patch.object(agent.thermal_checker, 'analyze', return_value=pass_result), \
             patch.object(agent.orbital_cycle, 'analyze', return_value=pass_result), \
             patch.object(agent.deployment, 'validate', return_value=pass_result), \
             patch.object(agent.kinematic, 'analyze', return_value=pass_result):

            results, summary = await agent.run_full_analysis(mass_budget=100.0)

        assert any(r.status == AnalysisStatus.FAIL for r in results)
        assert "FAIL" in summary

    @pytest.mark.asyncio
    async def test_run_full_analysis_continues_on_error(self, agent):
        """Full analysis continues running remaining analyzers even if one raises."""
        pass_result = AnalysisResult(
            analyzer="test", status=AnalysisStatus.PASS,
        )
        with patch.object(agent.mass_budget, 'analyze', side_effect=RuntimeError("neo4j down")), \
             patch.object(agent.cog, 'calculate', return_value=pass_result), \
             patch.object(agent.assembly, 'validate', return_value=pass_result), \
             patch.object(agent.thermal_solver, 'analyze', return_value=pass_result), \
             patch.object(agent.thermal_checker, 'analyze', return_value=pass_result), \
             patch.object(agent.orbital_cycle, 'analyze', return_value=pass_result), \
             patch.object(agent.deployment, 'validate', return_value=pass_result), \
             patch.object(agent.kinematic, 'analyze', return_value=pass_result):

            results, summary = await agent.run_full_analysis(mass_budget=100.0)

        # Should still have results from the other analyzers, plus an error result
        assert len(results) == 8
        assert any(r.status == AnalysisStatus.FAIL for r in results)

    @pytest.mark.asyncio
    async def test_run_structural_only(self, agent):
        """Can run only structural analyses."""
        pass_result = AnalysisResult(
            analyzer="test", status=AnalysisStatus.PASS,
        )
        with patch.object(agent.mass_budget, 'analyze', return_value=pass_result), \
             patch.object(agent.cog, 'calculate', return_value=pass_result), \
             patch.object(agent.assembly, 'validate', return_value=pass_result):

            results, summary = await agent.run_structural(mass_budget=100.0)

        assert len(results) == 3
