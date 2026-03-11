"""Tests for assembly tree validator."""
import pytest
from unittest.mock import AsyncMock

from src.plugins.sat_maestro.mechanical.structural.assembly_validator import AssemblyValidator
from src.plugins.sat_maestro.core.graph_models import AnalysisStatus, Severity


class TestAssemblyValidator:

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def validator(self, mock_bridge):
        return AssemblyValidator(mock_bridge)

    @pytest.mark.asyncio
    async def test_valid_assembly_tree(self, validator, mock_bridge):
        """No violations for a well-formed tree."""
        # No cycles
        mock_bridge.neo4j_query.side_effect = [
            [],  # cycle check returns no cycles
            [],  # orphan structures check returns none
            [],  # missing materials check returns none
            [],  # mass rollup inconsistencies returns none
        ]
        result = await validator.validate()
        assert result.status == AnalysisStatus.PASS
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_cycle_detected(self, validator, mock_bridge):
        """ERROR when assembly hierarchy has a cycle."""
        mock_bridge.neo4j_query.side_effect = [
            [{"path": "A->B->A"}],  # cycle found
            [],  # orphan check
            [],  # material check
            [],  # mass rollup check
        ]
        result = await validator.validate()
        assert result.status == AnalysisStatus.FAIL
        assert any(v.severity == Severity.ERROR and "cycle" in v.message.lower()
                    for v in result.violations)

    @pytest.mark.asyncio
    async def test_orphan_structures(self, validator, mock_bridge):
        """WARNING when structures don't belong to any assembly."""
        mock_bridge.neo4j_query.side_effect = [
            [],  # no cycles
            [{"name": "bracket_1"}, {"name": "panel_2"}],  # orphan structures
            [],  # material check
            [],  # mass rollup check
        ]
        result = await validator.validate()
        assert any(v.severity == Severity.WARNING and "orphan" in v.message.lower()
                    for v in result.violations)

    @pytest.mark.asyncio
    async def test_missing_material(self, validator, mock_bridge):
        """ERROR when structure references non-existent material."""
        mock_bridge.neo4j_query.side_effect = [
            [],  # no cycles
            [],  # no orphans
            [{"struct_name": "panel_1", "material": "unobtanium"}],  # missing material
            [],  # mass rollup check
        ]
        result = await validator.validate()
        assert result.status == AnalysisStatus.FAIL
        assert any(v.severity == Severity.ERROR and "material" in v.message.lower()
                    for v in result.violations)

    @pytest.mark.asyncio
    async def test_mass_rollup_inconsistency(self, validator, mock_bridge):
        """WARNING when assembly total_mass doesn't match sum of children."""
        mock_bridge.neo4j_query.side_effect = [
            [],  # no cycles
            [],  # no orphans
            [],  # no missing materials
            [{"name": "EPS", "total_mass": 10.0, "child_sum": 8.0}],  # inconsistent
        ]
        result = await validator.validate()
        assert any(v.severity == Severity.WARNING and "mass" in v.message.lower()
                    for v in result.violations)

    @pytest.mark.asyncio
    async def test_empty_graph(self, validator, mock_bridge):
        """Handles empty graph gracefully."""
        mock_bridge.neo4j_query.side_effect = [
            [],  # no cycles
            [],  # no orphans
            [],  # no missing materials
            [],  # no mass rollup issues
        ]
        result = await validator.validate()
        assert result.status == AnalysisStatus.PASS
