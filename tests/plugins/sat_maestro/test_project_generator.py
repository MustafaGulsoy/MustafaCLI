"""Tests for the CubeSat project documentation generator."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from src.plugins.sat_maestro.core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from src.plugins.sat_maestro.cubesat_wizard import CubeSatDesign
from src.plugins.sat_maestro.docs.project_generator import (
    DocsResult,
    ProjectDocGenerator,
    _build_action_items,
    _build_recommendations,
    _complexity_score,
    _estimate_weeks,
    _friendly_analyzer,
    _get_component_property,
    _mass_margin_pct,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_design() -> CubeSatDesign:
    """Minimal 1U design with only EPS + OBC."""
    return CubeSatDesign(
        mission_name="TestSat-1",
        sat_size="1U",
        orbit_type="LEO",
        orbit_altitude=500,
        orbit_inclination=51.6,
        design_life=1.0,
        payload_type="Technology Demo",
        payload_power=1.0,
        payload_mass=50,
        subsystems=["eps", "obc"],
        solar_config="Body-mounted",
        battery_type="Li-ion 18650",
        data_budget=10,
    )


@pytest.fixture
def full_design() -> CubeSatDesign:
    """Full 3U design with all common subsystems."""
    return CubeSatDesign(
        mission_name="TurkSat-Nano-1",
        sat_size="3U",
        orbit_type="SSO",
        orbit_altitude=550,
        orbit_inclination=97.5,
        design_life=3.0,
        payload_type="Camera (EO)",
        payload_power=8.0,
        payload_mass=300,
        subsystems=["eps", "obc", "com_uhf", "com_sband", "adcs", "gps"],
        solar_config="Deployable 2-panel",
        battery_type="Li-ion 18650",
        data_budget=500,
    )


@pytest.fixture
def pass_results() -> list[AnalysisResult]:
    """Analysis results where everything passes."""
    return [
        AnalysisResult(
            analyzer="mass_budget",
            status=AnalysisStatus.PASS,
            timestamp=datetime.now(),
            violations=[],
            summary={"total_mass": 1.2, "budget": 4.0},
        ),
        AnalysisResult(
            analyzer="power_budget",
            status=AnalysisStatus.PASS,
            timestamp=datetime.now(),
            violations=[],
            summary={
                "total_consumption_w": 5.0,
                "total_generation_w": 12.0,
                "avg_generation_w": 7.2,
                "sunlit_fraction": 0.6,
                "orbit_avg_limit_w": 8.0,
                "margin": 0.3,
                "component_count": 10,
            },
        ),
        AnalysisResult(
            analyzer="pin_voltage_check",
            status=AnalysisStatus.PASS,
            timestamp=datetime.now(),
            violations=[],
            summary={"total_connections": 20, "ok_connections": 20, "mismatches": 0},
        ),
        AnalysisResult(
            analyzer="thermal_node_model",
            status=AnalysisStatus.PASS,
            timestamp=datetime.now(),
            violations=[],
            summary={"min_temp": -30.0, "max_temp": 60.0, "node_count": 8},
        ),
        AnalysisResult(
            analyzer="thermal_checker",
            status=AnalysisStatus.PASS,
            timestamp=datetime.now(),
            violations=[],
            summary={"nodes_checked": 8, "errors": 0, "warnings": 0},
        ),
    ]


@pytest.fixture
def warn_results() -> list[AnalysisResult]:
    """Analysis results with warnings on power budget."""
    return [
        AnalysisResult(
            analyzer="mass_budget",
            status=AnalysisStatus.PASS,
            timestamp=datetime.now(),
            violations=[],
            summary={"total_mass": 1.2, "budget": 4.0},
        ),
        AnalysisResult(
            analyzer="power_budget",
            status=AnalysisStatus.WARN,
            timestamp=datetime.now(),
            violations=[
                Violation(
                    rule_id="POWER-BUDGET-001",
                    severity=Severity.WARNING,
                    message="Power consumption 11.7 W exceeds orbit-avg generation 4.2 W",
                    component_path="spacecraft/power",
                    details={},
                ),
            ],
            summary={
                "total_consumption_w": 11.7,
                "total_generation_w": 7.0,
                "avg_generation_w": 4.2,
                "sunlit_fraction": 0.6,
                "orbit_avg_limit_w": 8.0,
                "margin": -1.78,
                "component_count": 10,
            },
        ),
    ]


@pytest.fixture
def fail_results() -> list[AnalysisResult]:
    """Analysis results with a pin voltage FAIL."""
    return [
        AnalysisResult(
            analyzer="pin_voltage_check",
            status=AnalysisStatus.FAIL,
            timestamp=datetime.now(),
            violations=[
                Violation(
                    rule_id="PIN-VOLTAGE-001",
                    severity=Severity.ERROR,
                    message="Voltage mismatch: EPS_OUT (7.40 V) -> OBC_IN (3.30 V)",
                    component_path="eps_pcu->obc_main",
                    details={},
                ),
            ],
            summary={"total_connections": 10, "ok_connections": 9, "mismatches": 1},
        ),
    ]


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Temporary output directory for generated files."""
    return tmp_path / "cubesat_docs"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for internal helper functions."""

    def test_mass_margin_pct(self, minimal_design: CubeSatDesign) -> None:
        margin = _mass_margin_pct(minimal_design)
        # 1U limit = 1330g, minimal design mass should be well under
        assert 0 < margin < 100

    def test_mass_margin_full_design(self, full_design: CubeSatDesign) -> None:
        margin = _mass_margin_pct(full_design)
        # 3U limit = 4000g
        assert margin > 0

    def test_complexity_score_increases_with_subsystems(self) -> None:
        small = CubeSatDesign(subsystems=["eps", "obc"], sat_size="1U")
        large = CubeSatDesign(
            subsystems=["eps", "obc", "com_uhf", "adcs", "propulsion"],
            sat_size="3U",
        )
        assert _complexity_score(large) > _complexity_score(small)

    def test_estimate_weeks_returns_all_phases(self, minimal_design: CubeSatDesign) -> None:
        weeks = _estimate_weeks(minimal_design)
        assert set(weeks.keys()) == {
            "concept", "detailed_design", "firmware",
            "integration_test", "launch_prep",
        }
        for v in weeks.values():
            assert v >= 2

    def test_friendly_analyzer_known(self) -> None:
        assert _friendly_analyzer("mass_budget") == "Mass Budget"
        assert _friendly_analyzer("power_budget") == "Power Budget"

    def test_friendly_analyzer_unknown(self) -> None:
        assert _friendly_analyzer("custom_check") == "custom_check"

    def test_get_component_property_found(self, full_design: CubeSatDesign) -> None:
        freq = _get_component_property(full_design, "com_uhf_trx", "freq_mhz")
        assert freq == 437

    def test_get_component_property_missing(self, minimal_design: CubeSatDesign) -> None:
        result = _get_component_property(minimal_design, "nonexistent", "foo")
        assert result is None


# ---------------------------------------------------------------------------
# Recommendation and action item tests
# ---------------------------------------------------------------------------


class TestRecommendations:
    """Tests for the recommendation engine."""

    def test_low_mass_margin_recommendation(self) -> None:
        heavy = CubeSatDesign(
            sat_size="1U",
            payload_mass=1100,  # Nearly fills a 1U
            subsystems=["eps", "obc"],
        )
        recs = _build_recommendations(heavy, [])
        assert any("mass margin" in r.lower() for r in recs)

    def test_power_warning_recommendation(self, full_design: CubeSatDesign, warn_results: list[AnalysisResult]) -> None:
        recs = _build_recommendations(full_design, warn_results)
        assert any("power" in r.lower() for r in recs)

    def test_high_altitude_no_propulsion_recommendation(self) -> None:
        design = CubeSatDesign(
            orbit_altitude=700,
            subsystems=["eps", "obc"],
        )
        recs = _build_recommendations(design, [])
        assert any("deorbit" in r.lower() for r in recs)

    def test_high_data_no_sband_recommendation(self) -> None:
        design = CubeSatDesign(
            data_budget=1000,
            subsystems=["eps", "obc", "com_uhf"],
        )
        recs = _build_recommendations(design, [])
        assert any("s-band" in r.lower() for r in recs)

    def test_no_recommendations_for_nominal(
        self, full_design: CubeSatDesign, pass_results: list[AnalysisResult]
    ) -> None:
        # Full design with S-Band and altitude < 600
        design = CubeSatDesign(
            sat_size="3U",
            orbit_altitude=500,
            subsystems=["eps", "obc", "com_uhf", "com_sband", "adcs"],
            solar_config="Deployable 2-panel",
            data_budget=100,
        )
        recs = _build_recommendations(design, pass_results)
        # May still have mass margin recommendation, but no critical ones
        assert not any("deorbit" in r.lower() for r in recs)

    def test_action_items_from_errors(
        self, full_design: CubeSatDesign, fail_results: list[AnalysisResult]
    ) -> None:
        items = _build_action_items(full_design, fail_results)
        high_items = [i for i, p in items if p == "HIGH"]
        assert len(high_items) >= 1

    def test_action_items_from_warnings(
        self, full_design: CubeSatDesign, warn_results: list[AnalysisResult]
    ) -> None:
        items = _build_action_items(full_design, warn_results)
        medium_items = [i for i, p in items if p == "MEDIUM"]
        assert len(medium_items) >= 1


# ---------------------------------------------------------------------------
# Document generation tests
# ---------------------------------------------------------------------------


class TestProjectTracker:
    """Tests for project_tracker.md generation."""

    def test_generates_tracker_file(
        self, full_design: CubeSatDesign, pass_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, pass_results)
        result = gen.generate(output_dir)
        assert os.path.exists(result.tracker_file)
        assert result.tracker_file.endswith("project_tracker.md")

    def test_tracker_contains_mission_name(
        self, full_design: CubeSatDesign, pass_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, pass_results)
        result = gen.generate(output_dir)
        content = Path(result.tracker_file).read_text(encoding="utf-8")
        assert "TurkSat-Nano-1" in content

    def test_tracker_contains_mission_overview_table(
        self, full_design: CubeSatDesign, pass_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, pass_results)
        gen.generate(output_dir)
        content = (output_dir / "project_tracker.md").read_text(encoding="utf-8")
        assert "## Mission Overview" in content
        assert "3U" in content
        assert "SSO 550km" in content
        assert "3.0 years" in content

    def test_tracker_subsystem_specific_firmware_items(
        self, minimal_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(minimal_design)
        gen.generate(output_dir)
        content = (output_dir / "project_tracker.md").read_text(encoding="utf-8")
        # minimal design has eps + obc only
        assert "EPS driver tested" in content
        assert "OBC firmware skeleton" in content
        # Should NOT have ADCS or COM items
        assert "ADCS interface tested" not in content
        assert "UHF COM driver tested" not in content

    def test_tracker_with_warnings_shows_open_issues(
        self, full_design: CubeSatDesign, warn_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, warn_results)
        gen.generate(output_dir)
        content = (output_dir / "project_tracker.md").read_text(encoding="utf-8")
        assert "Open Issues" in content
        assert "POWER-BUDGET-001" in content or "Power consumption" in content

    def test_tracker_without_results_omits_analysis_section(
        self, minimal_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(minimal_design, analysis_results=[])
        gen.generate(output_dir)
        content = (output_dir / "project_tracker.md").read_text(encoding="utf-8")
        assert "## Analysis Results Summary" not in content

    def test_power_issue_checkbox_present_on_warn(
        self, full_design: CubeSatDesign, warn_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, warn_results)
        gen.generate(output_dir)
        content = (output_dir / "project_tracker.md").read_text(encoding="utf-8")
        assert "Power budget issue resolved" in content

    def test_pin_voltage_issue_in_integration_phase(
        self, full_design: CubeSatDesign, fail_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, fail_results)
        gen.generate(output_dir)
        content = (output_dir / "project_tracker.md").read_text(encoding="utf-8")
        assert "Pin voltage mismatches resolved" in content


class TestTimeline:
    """Tests for timeline.md generation."""

    def test_generates_timeline_file(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        result = gen.generate(output_dir)
        timeline_path = output_dir / "timeline.md"
        assert timeline_path.exists()
        assert str(timeline_path) in result.files

    def test_timeline_contains_all_phases(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "timeline.md").read_text(encoding="utf-8")
        assert "Phase 1: Concept Design" in content
        assert "Phase 2: Detailed Design" in content
        assert "Phase 3: Firmware Development" in content
        assert "Phase 4: Integration & Test" in content
        assert "Phase 5: Launch Preparation" in content

    def test_timeline_has_milestones(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "timeline.md").read_text(encoding="utf-8")
        assert "CoDR" in content
        assert "PDR" in content
        assert "CDR" in content
        assert "LRR" in content

    def test_timeline_has_visual(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "timeline.md").read_text(encoding="utf-8")
        assert "Visual Timeline" in content
        assert "```" in content


class TestDesignReview:
    """Tests for design_review.md generation."""

    def test_design_review_overall_pass(
        self, full_design: CubeSatDesign, pass_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, pass_results)
        gen.generate(output_dir)
        content = (output_dir / "design_review.md").read_text(encoding="utf-8")
        assert "PASS -- All analyses within acceptable limits" in content

    def test_design_review_conditional_pass(
        self, full_design: CubeSatDesign, warn_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, warn_results)
        gen.generate(output_dir)
        content = (output_dir / "design_review.md").read_text(encoding="utf-8")
        assert "CONDITIONAL PASS" in content

    def test_design_review_fail(
        self, full_design: CubeSatDesign, fail_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, fail_results)
        gen.generate(output_dir)
        content = (output_dir / "design_review.md").read_text(encoding="utf-8")
        assert "FAIL -- Critical issues" in content

    def test_design_review_component_table(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "design_review.md").read_text(encoding="utf-8")
        assert "Component Breakdown" in content
        assert "TOTAL" in content

    def test_design_review_no_results_message(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, analysis_results=[])
        gen.generate(output_dir)
        content = (output_dir / "design_review.md").read_text(encoding="utf-8")
        assert "No analysis results available" in content

    def test_design_review_violations_table(
        self, full_design: CubeSatDesign, fail_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, fail_results)
        gen.generate(output_dir)
        content = (output_dir / "design_review.md").read_text(encoding="utf-8")
        assert "Violations" in content
        assert "PIN-VOLTAGE-001" in content

    def test_design_review_recommendations_section(
        self, full_design: CubeSatDesign, warn_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, warn_results)
        gen.generate(output_dir)
        content = (output_dir / "design_review.md").read_text(encoding="utf-8")
        assert "Recommendations" in content


class TestTestPlan:
    """Tests for test_plan.md generation."""

    def test_test_plan_references_ecss(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "test_plan.md").read_text(encoding="utf-8")
        assert "ECSS-E-ST-10-03C" in content

    def test_test_plan_has_functional_tests(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "test_plan.md").read_text(encoding="utf-8")
        assert "Functional Tests" in content
        assert "Battery charge/discharge" in content
        assert "Boot sequence" in content
        # full_design has com_uhf
        assert "TX power output" in content

    def test_test_plan_subsystem_specific(
        self, minimal_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(minimal_design)
        gen.generate(output_dir)
        content = (output_dir / "test_plan.md").read_text(encoding="utf-8")
        # minimal has eps + obc, no ADCS
        assert "Battery charge/discharge" in content
        assert "Magnetorquer actuation" not in content

    def test_test_plan_tvac_section(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "test_plan.md").read_text(encoding="utf-8")
        assert "Thermal Vacuum" in content
        assert "Qualification" in content
        assert "Acceptance" in content

    def test_test_plan_vibration_section(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "test_plan.md").read_text(encoding="utf-8")
        assert "Vibration Testing" in content
        assert "gRMS" in content

    def test_test_plan_emc_uhf(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "test_plan.md").read_text(encoding="utf-8")
        assert "UHF TX spurious" in content

    def test_test_plan_emc_sband(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "test_plan.md").read_text(encoding="utf-8")
        assert "S-Band TX spurious" in content

    def test_test_plan_integration_sequence(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "test_plan.md").read_text(encoding="utf-8")
        assert "Flat-sat assembly" in content
        assert "Day-in-the-life test" in content


class TestRequirements:
    """Tests for requirements.md generation."""

    def test_requirements_mass_section(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "Mass Requirements" in content
        assert "4.00 kg" in content  # 3U limit

    def test_requirements_power_section(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "Power Requirements" in content
        assert "8.0 W limit" in content  # 3U orbit avg limit

    def test_requirements_comm_uhf(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "437 MHz" in content
        assert "9.6 kbps" in content

    def test_requirements_comm_sband(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "2.0 Mbps" in content or "2.4 GHz" in content

    def test_requirements_adcs_section(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "Pointing Requirements" in content
        assert "1.0 deg" in content

    def test_requirements_environmental_section(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "Environmental Requirements" in content
        assert "Operating temperature" in content
        assert "Radiation tolerance" in content

    def test_requirements_no_adcs_section_without_adcs(
        self, minimal_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(minimal_design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "Pointing Requirements" not in content

    def test_requirements_deorbit_low_altitude(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "Natural decay" in content

    def test_requirements_deorbit_high_altitude_no_propulsion(
        self, output_dir: Path
    ) -> None:
        design = CubeSatDesign(
            orbit_altitude=700,
            subsystems=["eps", "obc"],
        )
        gen = ProjectDocGenerator(design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "REQUIRES ASSESSMENT" in content

    def test_requirements_propulsion_section(
        self, output_dir: Path
    ) -> None:
        design = CubeSatDesign(
            subsystems=["eps", "obc", "propulsion"],
        )
        gen = ProjectDocGenerator(design)
        gen.generate(output_dir)
        content = (output_dir / "requirements.md").read_text(encoding="utf-8")
        assert "Propulsion Requirements" in content
        assert "15 m/s" in content
        assert "65 s" in content


# ---------------------------------------------------------------------------
# Integration-level tests
# ---------------------------------------------------------------------------


class TestProjectDocGenerator:
    """Integration tests for the full generator."""

    def test_generates_all_five_files(
        self, full_design: CubeSatDesign, pass_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, pass_results)
        result = gen.generate(output_dir)
        assert len(result.files) == 5
        expected_names = {
            "project_tracker.md",
            "timeline.md",
            "design_review.md",
            "test_plan.md",
            "requirements.md",
        }
        actual_names = {Path(f).name for f in result.files}
        assert actual_names == expected_names

    def test_all_files_exist_on_disk(
        self, full_design: CubeSatDesign, pass_results: list[AnalysisResult], output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design, pass_results)
        result = gen.generate(output_dir)
        for f in result.files:
            assert Path(f).exists()
            assert Path(f).stat().st_size > 0

    def test_docs_result_dataclass(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        result = gen.generate(output_dir)
        assert isinstance(result, DocsResult)
        assert isinstance(result.files, list)
        assert isinstance(result.tracker_file, str)

    def test_creates_output_dir_if_missing(
        self, full_design: CubeSatDesign, tmp_path: Path
    ) -> None:
        nested = tmp_path / "deep" / "nested" / "docs"
        gen = ProjectDocGenerator(full_design)
        result = gen.generate(nested)
        assert nested.exists()
        assert len(result.files) == 5

    def test_overwrites_existing_files(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "project_tracker.md").write_text("old content", encoding="utf-8")
        gen = ProjectDocGenerator(full_design)
        gen.generate(output_dir)
        content = (output_dir / "project_tracker.md").read_text(encoding="utf-8")
        assert "old content" not in content
        assert full_design.mission_name in content

    def test_without_analysis_results(
        self, full_design: CubeSatDesign, output_dir: Path
    ) -> None:
        gen = ProjectDocGenerator(full_design)
        result = gen.generate(output_dir)
        assert len(result.files) == 5
        # Design review should indicate no results
        content = (output_dir / "design_review.md").read_text(encoding="utf-8")
        assert "No analysis results available" in content

    def test_with_skipped_analysis(self, full_design: CubeSatDesign, output_dir: Path) -> None:
        skipped = [
            AnalysisResult(
                analyzer="thermal_node_model",
                status=AnalysisStatus.WARN,
                timestamp=datetime.now(),
                violations=[
                    Violation(
                        rule_id="THERMAL_NODE_MODEL-RUNTIME",
                        severity=Severity.WARNING,
                        message="Analyzer could not run: Neo4j not available",
                        component_path="auto_analysis",
                    )
                ],
                summary={"skipped": True, "reason": "Neo4j not available"},
            ),
        ]
        gen = ProjectDocGenerator(full_design, skipped)
        gen.generate(output_dir)
        review = (output_dir / "design_review.md").read_text(encoding="utf-8")
        assert "Skipped" in review

    def test_minimal_vs_full_design_content_differs(
        self,
        minimal_design: CubeSatDesign,
        full_design: CubeSatDesign,
        tmp_path: Path,
    ) -> None:
        dir_min = tmp_path / "minimal"
        dir_full = tmp_path / "full"

        ProjectDocGenerator(minimal_design).generate(dir_min)
        ProjectDocGenerator(full_design).generate(dir_full)

        tracker_min = (dir_min / "project_tracker.md").read_text(encoding="utf-8")
        tracker_full = (dir_full / "project_tracker.md").read_text(encoding="utf-8")

        # Full design should have more content
        assert len(tracker_full) > len(tracker_min)
        # Full design has ADCS items, minimal does not
        assert "ADCS" not in tracker_min
        assert "ADCS" in tracker_full
