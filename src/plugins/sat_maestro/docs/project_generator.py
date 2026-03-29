"""Project tracker and documentation generator for the CubeSat auto-design pipeline.

Generates five markdown documents from a ``CubeSatDesign`` and optional
``AnalysisResult`` list:

1. **project_tracker.md** -- main phase checklist with live budget status
2. **timeline.md** -- milestone timeline scaled by satellite complexity
3. **design_review.md** -- pass/fail analysis summary with recommendations
4. **test_plan.md** -- ECSS-E-ST-10-03C derived test matrix
5. **requirements.md** -- auto-generated system-level requirements
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..core.graph_models import AnalysisResult, AnalysisStatus, Severity, Violation
from ..cubesat_wizard import COMPONENT_CATALOG, SIZE_LIMITS, CubeSatDesign


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class DocsResult:
    """Result payload returned after document generation."""

    files: list[str]
    tracker_file: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Subsystem human-readable names used for checklist items
_SUBSYSTEM_LABELS: dict[str, str] = {
    "eps": "EPS (Power System)",
    "obc": "OBC (On-Board Computer)",
    "com_uhf": "UHF Communication",
    "com_sband": "S-Band Communication",
    "adcs": "ADCS (Attitude Control)",
    "gps": "GPS Receiver",
    "propulsion": "Propulsion",
    "thermal": "Active Thermal Control",
}

# Complexity weight per subsystem (used to estimate timeline)
_SUBSYSTEM_COMPLEXITY: dict[str, float] = {
    "eps": 1.0,
    "obc": 1.5,
    "com_uhf": 1.0,
    "com_sband": 1.5,
    "adcs": 2.0,
    "gps": 0.5,
    "propulsion": 2.5,
    "thermal": 1.0,
}

# Base durations in weeks per phase for a minimal 1U satellite
_BASE_WEEKS: dict[str, int] = {
    "concept": 4,
    "detailed_design": 10,
    "firmware": 12,
    "integration_test": 8,
    "launch_prep": 6,
}

# Size multiplier for schedule estimation
_SIZE_MULTIPLIER: dict[str, float] = {
    "1U": 1.0,
    "2U": 1.15,
    "3U": 1.3,
    "6U": 1.6,
    "12U": 2.0,
}

# Orbit thermal approximations (hot/cold case in degrees C)
_ORBIT_THERMAL: dict[str, tuple[float, float]] = {
    "LEO": (-40.0, 80.0),
    "SSO": (-60.0, 70.0),
    "MEO": (-80.0, 90.0),
    "GTO": (-120.0, 120.0),
}


def _status_icon(status: AnalysisStatus) -> str:
    """Return a markdown-friendly status label."""
    return {
        AnalysisStatus.PASS: "PASS",
        AnalysisStatus.WARN: "WARN",
        AnalysisStatus.FAIL: "FAIL",
    }[status]


def _check(done: bool) -> str:
    """Return a markdown checkbox string."""
    return "[x]" if done else "[ ]"


def _find_result(
    results: list[AnalysisResult], analyzer: str
) -> AnalysisResult | None:
    """Locate a result by analyzer name."""
    for r in results:
        if r.analyzer == analyzer:
            return r
    return None


def _mass_margin_pct(design: CubeSatDesign) -> float:
    """Compute mass margin as a percentage of the size-class limit."""
    limit_g = design.limits["max_mass_kg"] * 1000
    used_g = design.total_mass_g()
    if limit_g == 0:
        return 0.0
    return (limit_g - used_g) / limit_g * 100


def _power_consumption(design: CubeSatDesign) -> float:
    """Total power draw from all consumers (positive power_w)."""
    return design.total_power_w()


def _orbit_description(design: CubeSatDesign) -> str:
    """Human-readable orbit string."""
    return f"{design.orbit_type} {design.orbit_altitude:.0f}km"


def _complexity_score(design: CubeSatDesign) -> float:
    """Compute a unitless complexity score for timeline scaling."""
    base = sum(
        _SUBSYSTEM_COMPLEXITY.get(ss, 1.0) for ss in design.subsystems
    )
    size_mult = _SIZE_MULTIPLIER.get(design.sat_size, 1.0)
    return base * size_mult


def _estimate_weeks(design: CubeSatDesign) -> dict[str, int]:
    """Estimate phase durations in weeks based on design complexity."""
    score = _complexity_score(design)
    # Normalize against a typical 1U (eps+obc+com_uhf+adcs = 5.5 complexity)
    factor = max(score / 5.5, 1.0)
    return {
        phase: max(2, math.ceil(base * factor))
        for phase, base in _BASE_WEEKS.items()
    }


# ---------------------------------------------------------------------------
# Document generators
# ---------------------------------------------------------------------------


def _generate_project_tracker(
    design: CubeSatDesign,
    results: list[AnalysisResult],
) -> str:
    """Generate ``project_tracker.md`` content."""
    limits = design.limits
    total_mass = design.total_mass_g()
    mass_limit_g = limits["max_mass_kg"] * 1000
    mass_margin = _mass_margin_pct(design)
    total_power = _power_consumption(design)
    orbit_avg_limit = limits["max_power_orbit_avg_w"]

    # Determine analysis statuses
    mass_result = _find_result(results, "mass_budget")
    power_result = _find_result(results, "power_budget")
    pin_result = _find_result(results, "pin_voltage_check")
    thermal_result = _find_result(results, "thermal_node_model")
    thermal_check_result = _find_result(results, "thermal_checker")

    mass_status = _status_icon(mass_result.status) if mass_result else "N/A"
    power_status = _status_icon(power_result.status) if power_result else "N/A"

    # Phase 1 items are considered done if we have analysis results
    has_results = len(results) > 0
    mission_defined = True  # Always true if we have a design
    subsystem_selected = True

    mass_pass = mass_result and mass_result.status == AnalysisStatus.PASS if mass_result else False
    power_pass = power_result and power_result.status == AnalysisStatus.PASS if power_result else False
    power_issue_exists = power_result and power_result.status != AnalysisStatus.PASS if power_result else False

    lines: list[str] = []
    lines.append(f"# {design.mission_name} — CubeSat Project Tracker")
    lines.append("")
    lines.append("## Mission Overview")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Size | {design.sat_size} |")
    lines.append(f"| Orbit | {_orbit_description(design)} |")
    lines.append(f"| Design Life | {design.design_life} years |")
    lines.append(f"| Total Mass | {total_mass:.0f}g / {mass_limit_g:.0f}g limit |")
    lines.append(f"| Payload | {design.payload_type} ({design.payload_power}W) |")
    lines.append(f"| Solar Config | {design.solar_config} |")
    lines.append(f"| Battery | {design.battery_type} |")
    lines.append(f"| Daily Data Budget | {design.data_budget:.0f} MB |")
    lines.append("")

    # ---- Phase 1: Concept Design ----
    phase1_items_done = sum([mission_defined, subsystem_selected, has_results])
    phase1_total = 3  # base items before conditional ones
    conditional_items: list[tuple[str, bool]] = []

    # Mass budget line
    if mass_result:
        mass_label = f"Mass budget analysis — {mass_status} ({mass_margin:.1f}% margin)"
        conditional_items.append((mass_label, True))
        phase1_total += 1
        phase1_items_done += 1
    else:
        conditional_items.append(("Mass budget analysis", False))
        phase1_total += 1

    # Power budget line
    if power_result:
        pwr_detail = f"{total_power:.1f}W / {orbit_avg_limit:.1f}W avg"
        power_label = f"Power budget analysis — {power_status} ({pwr_detail})"
        conditional_items.append((power_label, True))
        phase1_total += 1
        phase1_items_done += 1
    else:
        conditional_items.append(("Power budget analysis", False))
        phase1_total += 1

    # Power issue resolution (only if there IS a power issue)
    if power_issue_exists:
        conditional_items.append(("Power budget issue resolved", False))
        phase1_total += 1

    all_phase1_done = phase1_items_done == phase1_total
    phase1_mark = "completed" if all_phase1_done else "in progress"
    lines.append("## Phase Checklist")
    lines.append("")
    lines.append(f"### Phase 1: Concept Design ({phase1_mark})")
    lines.append(f"- {_check(mission_defined)} Mission requirements defined")
    lines.append(f"- {_check(subsystem_selected)} Subsystem selection complete")

    for label, done in conditional_items:
        lines.append(f"- {_check(done)} {label}")

    lines.append("")

    # ---- Phase 2: Detailed Design ----
    lines.append("### Phase 2: Detailed Design")
    lines.append("- [ ] Electrical schematics complete")
    lines.append("- [ ] PCB layout started")
    lines.append("- [ ] 3D model finalized")

    # Only include thermal/vibration items if relevant subsystems are present
    if "thermal" in design.subsystems or True:
        # Thermal analysis is always relevant for a satellite
        thermal_done = (
            thermal_result is not None
            and thermal_result.status == AnalysisStatus.PASS
        )
        thermal_label = "Thermal analysis passing"
        if thermal_result:
            thermal_label += f" — {_status_icon(thermal_result.status)}"
        lines.append(f"- {_check(thermal_done)} {thermal_label}")

    lines.append("- [ ] Vibration analysis complete")

    # Subsystem-specific design items
    for ss_id in design.subsystems:
        label = _SUBSYSTEM_LABELS.get(ss_id, ss_id)
        lines.append(f"- [ ] {label} detailed design review")

    lines.append("")

    # ---- Phase 3: Firmware Development ----
    lines.append("### Phase 3: Firmware Development")
    if "obc" in design.subsystems:
        lines.append("- [ ] OBC firmware skeleton generated")
    if "eps" in design.subsystems:
        lines.append("- [ ] EPS driver tested")
    if "com_uhf" in design.subsystems:
        lines.append("- [ ] UHF COM driver tested")
    if "com_sband" in design.subsystems:
        lines.append("- [ ] S-Band COM driver tested")
    if "adcs" in design.subsystems:
        lines.append("- [ ] ADCS interface tested")
    if "gps" in design.subsystems:
        lines.append("- [ ] GPS interface tested")
    if "propulsion" in design.subsystems:
        lines.append("- [ ] Propulsion interface tested")
    if "thermal" in design.subsystems:
        lines.append("- [ ] Thermal control driver tested")
    lines.append("- [ ] Payload interface tested")
    lines.append("")

    # ---- Phase 4: Integration & Test ----
    lines.append("### Phase 4: Integration & Test")
    lines.append("- [ ] Flat-sat integration")
    lines.append("- [ ] Functional testing")
    lines.append("- [ ] Environmental testing (thermal vacuum)")
    lines.append("- [ ] Vibration testing")
    lines.append("- [ ] EMC testing")
    if pin_result and pin_result.status != AnalysisStatus.PASS:
        lines.append("- [ ] Pin voltage mismatches resolved")
    lines.append("")

    # ---- Phase 5: Launch Preparation ----
    lines.append("### Phase 5: Launch Preparation")
    lines.append("- [ ] Flight model assembly")
    lines.append("- [ ] Final acceptance testing")
    lines.append("- [ ] Launcher interface verification")
    if "com_uhf" in design.subsystems or "com_sband" in design.subsystems:
        lines.append("- [ ] Frequency coordination")
    lines.append("- [ ] Launch campaign")
    lines.append("")

    # ---- Analysis Results Summary ----
    if results:
        lines.append("## Analysis Results Summary")
        lines.append("| Analysis | Status | Detail |")
        lines.append("|----------|--------|--------|")
        for r in results:
            detail = _analysis_detail_brief(r)
            lines.append(f"| {_friendly_analyzer(r.analyzer)} | {_status_icon(r.status)} | {detail} |")
        lines.append("")

        # Open issues
        all_violations = [v for r in results for v in r.violations]
        if all_violations:
            lines.append("## Open Issues")
            for i, v in enumerate(all_violations, 1):
                lines.append(f"{i}. **[{v.severity.value}]** {v.message}")
            lines.append("")

    return "\n".join(lines)


def _generate_timeline(design: CubeSatDesign) -> str:
    """Generate ``timeline.md`` content."""
    weeks = _estimate_weeks(design)
    today = date.today()

    lines: list[str] = []
    lines.append(f"# {design.mission_name} — Project Timeline")
    lines.append("")
    lines.append(f"Generated: {today.isoformat()}")
    lines.append("")
    lines.append(f"Satellite: {design.sat_size} | Orbit: {_orbit_description(design)} "
                 f"| Design Life: {design.design_life} years")
    lines.append("")

    # Compute cumulative dates
    cursor = today
    phases: list[tuple[str, str, int, date, date]] = []
    phase_defs = [
        ("concept", "Phase 1: Concept Design"),
        ("detailed_design", "Phase 2: Detailed Design"),
        ("firmware", "Phase 3: Firmware Development"),
        ("integration_test", "Phase 4: Integration & Test"),
        ("launch_prep", "Phase 5: Launch Preparation"),
    ]

    for key, label in phase_defs:
        duration = weeks[key]
        start = cursor
        end = cursor + timedelta(weeks=duration)
        phases.append((key, label, duration, start, end))
        cursor = end

    total_weeks = sum(w for _, _, w, _, _ in phases)
    target_launch = cursor

    lines.append("## Schedule Overview")
    lines.append("")
    lines.append(f"| Total Duration | {total_weeks} weeks (~{total_weeks / 4:.0f} months) |")
    lines.append("|----------------|------|")
    lines.append(f"| Project Start  | {today.isoformat()} |")
    lines.append(f"| Target Launch  | {target_launch.isoformat()} |")
    lines.append("")

    lines.append("## Phase Timeline")
    lines.append("")
    lines.append("| Phase | Duration | Start | End |")
    lines.append("|-------|----------|-------|-----|")
    for _, label, duration, start, end in phases:
        lines.append(f"| {label} | {duration} weeks | {start.isoformat()} | {end.isoformat()} |")
    lines.append("")

    # Milestones
    lines.append("## Key Milestones")
    lines.append("")
    lines.append("| Milestone | Target Date |")
    lines.append("|-----------|-------------|")
    lines.append(f"| Concept Design Review (CoDR) | {phases[0][4].isoformat()} |")
    lines.append(f"| Preliminary Design Review (PDR) | {phases[1][4].isoformat()} |")
    lines.append(f"| Critical Design Review (CDR) | {phases[2][4].isoformat()} |")
    lines.append(f"| Test Readiness Review (TRR) | {phases[2][4].isoformat()} |")
    lines.append(f"| Flight Acceptance Review (FAR) | {phases[3][4].isoformat()} |")
    lines.append(f"| Launch Readiness Review (LRR) | {phases[4][4].isoformat()} |")
    lines.append("")

    # Gantt-like ASCII chart
    lines.append("## Visual Timeline")
    lines.append("")
    lines.append("```")
    bar_scale = max(1, total_weeks // 50)  # character per week-group
    for _, label, duration, _, _ in phases:
        bar_len = max(1, duration // bar_scale)
        bar = "=" * bar_len
        lines.append(f"{label:<40} |{bar}| {duration}w")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _generate_design_review(
    design: CubeSatDesign,
    results: list[AnalysisResult],
) -> str:
    """Generate ``design_review.md`` content."""
    lines: list[str] = []
    lines.append(f"# {design.mission_name} — Design Review Document")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()}")
    lines.append("")

    # Design summary
    lines.append("## 1. Design Summary")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Mission Name | {design.mission_name} |")
    lines.append(f"| Form Factor | {design.sat_size} |")
    lines.append(f"| Orbit | {design.orbit_type} {design.orbit_altitude:.0f}km, {design.orbit_inclination:.1f} deg |")
    lines.append(f"| Design Life | {design.design_life} years |")
    lines.append(f"| Payload | {design.payload_type} |")
    lines.append(f"| Payload Power | {design.payload_power} W |")
    lines.append(f"| Payload Mass | {design.payload_mass} g |")
    lines.append(f"| Solar Configuration | {design.solar_config} |")
    lines.append(f"| Battery Type | {design.battery_type} |")
    lines.append(f"| Daily Data Budget | {design.data_budget:.0f} MB |")
    lines.append("")

    # Subsystem selection
    lines.append("## 2. Selected Subsystems")
    lines.append("")
    for ss_id in design.subsystems:
        label = _SUBSYSTEM_LABELS.get(ss_id, ss_id)
        lines.append(f"- {label}")
    lines.append("")

    # Component breakdown
    lines.append("## 3. Component Breakdown")
    lines.append("")
    lines.append("| Component | Subsystem | Mass (g) | Power (W) |")
    lines.append("|-----------|-----------|----------|-----------|")
    for comp in design.get_all_components():
        pwr = f"{comp['power_w']:.1f}" if comp["power_w"] != 0 else "-"
        lines.append(f"| {comp['name']} | {comp['subsystem']} | {comp['mass_g']:.0f} | {pwr} |")
    lines.append(f"| **TOTAL** | | **{design.total_mass_g():.0f}** | **{design.total_power_w():.1f}** |")
    lines.append("")

    # Analysis results
    lines.append("## 4. Analysis Results")
    lines.append("")
    if not results:
        lines.append("_No analysis results available. Run the auto-analysis pipeline first._")
        lines.append("")
    else:
        # Overall verdict
        has_fail = any(r.status == AnalysisStatus.FAIL for r in results)
        has_warn = any(r.status == AnalysisStatus.WARN for r in results)
        if has_fail:
            verdict = "FAIL -- Critical issues must be resolved before proceeding."
        elif has_warn:
            verdict = "CONDITIONAL PASS -- Warnings should be addressed."
        else:
            verdict = "PASS -- All analyses within acceptable limits."
        lines.append(f"**Overall Verdict: {verdict}**")
        lines.append("")

        lines.append("| Analysis | Status | Summary |")
        lines.append("|----------|--------|---------|")
        for r in results:
            detail = _analysis_detail_brief(r)
            lines.append(f"| {_friendly_analyzer(r.analyzer)} | {_status_icon(r.status)} | {detail} |")
        lines.append("")

        # Detailed violations
        all_violations = [v for r in results for v in r.violations]
        if all_violations:
            lines.append("### 4.1 Violations")
            lines.append("")
            lines.append("| # | Severity | Rule | Message | Path |")
            lines.append("|---|----------|------|---------|------|")
            for i, v in enumerate(all_violations, 1):
                lines.append(f"| {i} | {v.severity.value} | {v.rule_id} | {v.message} | {v.component_path} |")
            lines.append("")

    # Recommendations
    lines.append("## 5. Recommendations")
    lines.append("")
    recommendations = _build_recommendations(design, results)
    if recommendations:
        for rec in recommendations:
            lines.append(f"- {rec}")
    else:
        lines.append("_No recommendations -- design is nominal._")
    lines.append("")

    # Open items
    lines.append("## 6. Open Items / Action Items")
    lines.append("")
    action_items = _build_action_items(design, results)
    if action_items:
        lines.append("| # | Action | Priority | Owner |")
        lines.append("|---|--------|----------|-------|")
        for i, (action, priority) in enumerate(action_items, 1):
            lines.append(f"| {i} | {action} | {priority} | TBD |")
    else:
        lines.append("_No open action items._")
    lines.append("")

    return "\n".join(lines)


def _generate_test_plan(design: CubeSatDesign) -> str:
    """Generate ``test_plan.md`` based on ECSS-E-ST-10-03C."""
    lines: list[str] = []
    lines.append(f"# {design.mission_name} — Test Plan")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()}")
    lines.append("")
    lines.append("Reference: ECSS-E-ST-10-03C (Testing)")
    lines.append("")

    # Test philosophy
    lines.append("## 1. Test Philosophy")
    lines.append("")
    lines.append("All testing follows the ECSS-E-ST-10-03C standard adapted for CubeSat missions.")
    lines.append("Qualification levels apply to the Engineering Model (EM). "
                 "Acceptance levels apply to the Flight Model (FM).")
    lines.append("")

    # Functional tests per subsystem
    lines.append("## 2. Functional Tests")
    lines.append("")
    lines.append("| Subsystem | Test | Level | Pass Criteria |")
    lines.append("|-----------|------|-------|---------------|")

    for ss_id in design.subsystems:
        label = _SUBSYSTEM_LABELS.get(ss_id, ss_id)
        for test_name, criteria in _functional_tests_for(ss_id):
            lines.append(f"| {label} | {test_name} | Unit | {criteria} |")

    # Payload functional test
    lines.append(f"| Payload ({design.payload_type}) | Power-on test | Unit | Nominal telemetry within spec |")
    lines.append(f"| Payload ({design.payload_type}) | Data output test | Unit | Data rate meets {design.data_budget:.0f} MB/day requirement |")
    lines.append("")

    # Environmental tests
    lines.append("## 3. Environmental Tests")
    lines.append("")

    # Thermal vacuum
    cold, hot = _ORBIT_THERMAL.get(design.orbit_type, (-40.0, 80.0))
    qual_cold = cold - 10
    qual_hot = hot + 10

    lines.append("### 3.1 Thermal Vacuum (TVAC)")
    lines.append("")
    lines.append("| Parameter | Qualification | Acceptance |")
    lines.append("|-----------|--------------|------------|")
    lines.append(f"| Hot case | {qual_hot:.0f} C | {hot:.0f} C |")
    lines.append(f"| Cold case | {qual_cold:.0f} C | {cold:.0f} C |")
    lines.append("| Cycles | 8 | 4 |")
    lines.append("| Dwell time | 4 hours | 2 hours |")
    lines.append(f"| Pressure | < 1e-5 mbar | < 1e-5 mbar |")
    lines.append("")

    # Vibration
    lines.append("### 3.2 Vibration Testing")
    lines.append("")
    lines.append("| Parameter | Qualification | Acceptance |")
    lines.append("|-----------|--------------|------------|")
    lines.append("| Sine sweep | 5-100 Hz, 1 oct/min | 5-100 Hz, 2 oct/min |")
    lines.append("| Random vib | 14.1 gRMS, 2 min/axis | 10.0 gRMS, 1 min/axis |")
    lines.append("| Axes | X, Y, Z | X, Y, Z |")
    lines.append("| Notching | First eigenfrequency | First eigenfrequency |")
    lines.append("")

    # EMC
    lines.append("### 3.3 EMC Testing")
    lines.append("")
    lines.append("| Test | Standard | Frequency Range |")
    lines.append("|------|----------|-----------------|")
    lines.append("| Conducted emissions | ECSS-E-ST-20-07C | 30 Hz - 50 MHz |")
    lines.append("| Radiated emissions | ECSS-E-ST-20-07C | 30 MHz - 18 GHz |")
    if "com_uhf" in design.subsystems:
        lines.append("| UHF TX spurious | ITU-R SM.329 | 430 - 440 MHz band |")
    if "com_sband" in design.subsystems:
        lines.append("| S-Band TX spurious | ITU-R SM.329 | 2.2 - 2.5 GHz band |")
    lines.append("")

    # Integration test sequence
    lines.append("## 4. Integration Test Sequence")
    lines.append("")
    lines.append("| Step | Test | Configuration |")
    lines.append("|------|------|---------------|")
    lines.append("| 1 | Flat-sat assembly | All boards on bench |")
    lines.append("| 2 | Power-on sequence | EPS + OBC only |")

    step = 3
    for ss_id in design.subsystems:
        if ss_id in ("eps", "obc"):
            continue
        label = _SUBSYSTEM_LABELS.get(ss_id, ss_id)
        lines.append(f"| {step} | {label} integration | Incremental add |")
        step += 1

    lines.append(f"| {step} | Payload integration | Full system |")
    step += 1
    lines.append(f"| {step} | End-to-end comm test | Ground station link |")
    step += 1
    lines.append(f"| {step} | Day-in-the-life test | Orbit simulation, 24h |")
    lines.append("")

    # Test matrix summary
    lines.append("## 5. Test Matrix Summary")
    lines.append("")
    lines.append("| Test Category | EM | FM |")
    lines.append("|---------------|----|----|")
    lines.append("| Functional | Qualification | Acceptance |")
    lines.append("| Thermal Vacuum | Qualification | Acceptance |")
    lines.append("| Vibration | Qualification | Acceptance |")
    lines.append("| EMC | Qualification | N/A |")
    lines.append("| Shock | Qualification | N/A |")
    lines.append("| Day-in-the-life | Full | Abbreviated |")
    lines.append("")

    return "\n".join(lines)


def _generate_requirements(design: CubeSatDesign) -> str:
    """Generate ``requirements.md`` from design parameters."""
    limits = design.limits
    mass_limit_kg = limits["max_mass_kg"]
    power_limit_w = limits["max_power_orbit_avg_w"]
    cold, hot = _ORBIT_THERMAL.get(design.orbit_type, (-40.0, 80.0))

    lines: list[str] = []
    lines.append(f"# {design.mission_name} — System Requirements")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()}")
    lines.append("")
    lines.append("Derived from CubeSat design parameters and ECSS/CDS standards.")
    lines.append("")

    req_num = 1

    # Mass requirements
    lines.append("## 1. Mass Requirements")
    lines.append("")
    lines.append("| Req ID | Requirement | Value | Source |")
    lines.append("|--------|-------------|-------|--------|")
    lines.append(f"| REQ-MASS-{req_num:03d} | Total spacecraft mass shall not exceed "
                 f"{design.sat_size} CDS limit | {mass_limit_kg:.2f} kg | CDS {design.sat_size} Spec |")
    req_num += 1
    lines.append(f"| REQ-MASS-{req_num:03d} | Mass margin shall be >= 20% at PDR | "
                 f"{_mass_margin_pct(design):.1f}% (current) | ECSS-M-ST-10C |")
    req_num += 1
    lines.append("")

    # Power requirements
    lines.append("## 2. Power Requirements")
    lines.append("")
    lines.append("| Req ID | Requirement | Value | Source |")
    lines.append("|--------|-------------|-------|--------|")
    lines.append(f"| REQ-PWR-{req_num:03d} | Orbit-average power consumption shall not "
                 f"exceed generation capacity | {power_limit_w:.1f} W limit | Design |")
    req_num += 1

    # Per-subsystem power allocation
    for ss_id in design.subsystems:
        if ss_id not in COMPONENT_CATALOG:
            continue
        ss_power = sum(
            c["power_w"]
            for c in COMPONENT_CATALOG[ss_id]["components"]
            if c["power_w"] > 0
        )
        if ss_power > 0:
            label = _SUBSYSTEM_LABELS.get(ss_id, ss_id)
            lines.append(
                f"| REQ-PWR-{req_num:03d} | {label} power allocation | "
                f"{ss_power:.1f} W | Component spec |"
            )
            req_num += 1

    lines.append(
        f"| REQ-PWR-{req_num:03d} | Payload power allocation | "
        f"{design.payload_power:.1f} W | Mission spec |"
    )
    req_num += 1

    # Battery capacity requirement
    batt_info = _get_component_property(design, "eps_batt", "capacity_wh")
    if batt_info is not None:
        lines.append(
            f"| REQ-PWR-{req_num:03d} | Battery capacity shall support "
            f"eclipse operations | {batt_info:.1f} Wh | Design |"
        )
        req_num += 1
    lines.append("")

    # Communication requirements
    lines.append("## 3. Communication Requirements")
    lines.append("")
    lines.append("| Req ID | Requirement | Value | Source |")
    lines.append("|--------|-------------|-------|--------|")

    if "com_uhf" in design.subsystems:
        uhf_rate = _get_component_property(design, "com_uhf_trx", "data_rate_kbps")
        uhf_freq = _get_component_property(design, "com_uhf_trx", "freq_mhz")
        uhf_power = _get_component_property(design, "com_uhf_trx", "tx_power_dbm")
        if uhf_rate:
            lines.append(
                f"| REQ-COM-{req_num:03d} | UHF uplink/downlink data rate | "
                f"{uhf_rate:.1f} kbps | Component spec |"
            )
            req_num += 1
        if uhf_freq:
            lines.append(
                f"| REQ-COM-{req_num:03d} | UHF operating frequency | "
                f"{uhf_freq:.0f} MHz | ITU allocation |"
            )
            req_num += 1
        if uhf_power:
            lines.append(
                f"| REQ-COM-{req_num:03d} | UHF TX power | "
                f"{uhf_power:.0f} dBm | Link budget |"
            )
            req_num += 1

    if "com_sband" in design.subsystems:
        sband_rate = _get_component_property(design, "com_sband_tx", "data_rate_mbps")
        sband_freq = _get_component_property(design, "com_sband_tx", "freq_ghz")
        if sband_rate:
            lines.append(
                f"| REQ-COM-{req_num:03d} | S-Band downlink data rate | "
                f"{sband_rate:.1f} Mbps | Component spec |"
            )
            req_num += 1
        if sband_freq:
            lines.append(
                f"| REQ-COM-{req_num:03d} | S-Band operating frequency | "
                f"{sband_freq:.1f} GHz | ITU allocation |"
            )
            req_num += 1

    lines.append(
        f"| REQ-COM-{req_num:03d} | Daily data downlink shall support payload budget | "
        f"{design.data_budget:.0f} MB/day | Mission spec |"
    )
    req_num += 1
    lines.append("")

    # Pointing requirements
    if "adcs" in design.subsystems:
        lines.append("## 4. Pointing Requirements")
        lines.append("")
        lines.append("| Req ID | Requirement | Value | Source |")
        lines.append("|--------|-------------|-------|--------|")
        pointing = _get_component_property(design, "adcs_unit", "pointing_accuracy_deg")
        if pointing:
            lines.append(
                f"| REQ-ADCS-{req_num:03d} | Pointing accuracy | "
                f"{pointing:.1f} deg (3-sigma) | ADCS spec |"
            )
            req_num += 1
        has_rw = _get_component_property(design, "adcs_unit", "reaction_wheels")
        if has_rw:
            lines.append(
                f"| REQ-ADCS-{req_num:03d} | Number of reaction wheels | "
                f"{has_rw} | Redundancy/performance |"
            )
            req_num += 1
        lines.append(
            f"| REQ-ADCS-{req_num:03d} | Detumbling shall complete within 3 orbits | "
            f"~270 min | Mission spec |"
        )
        req_num += 1
        lines.append("")

    # Environmental requirements
    lines.append("## 5. Environmental Requirements")
    lines.append("")
    lines.append("| Req ID | Requirement | Value | Source |")
    lines.append("|--------|-------------|-------|--------|")
    lines.append(
        f"| REQ-ENV-{req_num:03d} | Operating temperature range | "
        f"{cold:.0f} C to {hot:.0f} C | Orbit thermal analysis |"
    )
    req_num += 1
    lines.append(
        f"| REQ-ENV-{req_num:03d} | Survival temperature range | "
        f"{cold - 20:.0f} C to {hot + 20:.0f} C | Component limits |"
    )
    req_num += 1
    lines.append(
        f"| REQ-ENV-{req_num:03d} | Radiation tolerance (TID) | "
        f"{'> 10 krad' if design.orbit_altitude < 800 else '> 30 krad'} | "
        f"Orbit environment model |"
    )
    req_num += 1
    lines.append(
        f"| REQ-ENV-{req_num:03d} | Design life | "
        f"{design.design_life:.1f} years | Mission spec |"
    )
    req_num += 1

    if design.orbit_altitude < 600:
        lines.append(
            f"| REQ-ENV-{req_num:03d} | 25-year deorbit compliance | "
            f"Natural decay (alt < 600km) | IADC guidelines |"
        )
    elif "propulsion" in design.subsystems:
        lines.append(
            f"| REQ-ENV-{req_num:03d} | 25-year deorbit compliance | "
            f"Active deorbit via propulsion | IADC guidelines |"
        )
    else:
        lines.append(
            f"| REQ-ENV-{req_num:03d} | 25-year deorbit compliance | "
            f"REQUIRES ASSESSMENT (alt > 600km, no propulsion) | IADC guidelines |"
        )
    req_num += 1
    lines.append("")

    # Propulsion requirements (if selected)
    if "propulsion" in design.subsystems:
        lines.append("## 6. Propulsion Requirements")
        lines.append("")
        lines.append("| Req ID | Requirement | Value | Source |")
        lines.append("|--------|-------------|-------|--------|")
        delta_v = _get_component_property(design, "prop_unit", "delta_v_ms")
        isp = _get_component_property(design, "prop_unit", "isp_s")
        if delta_v:
            lines.append(
                f"| REQ-PROP-{req_num:03d} | Total delta-V capability | "
                f"{delta_v:.0f} m/s | Propulsion spec |"
            )
            req_num += 1
        if isp:
            lines.append(
                f"| REQ-PROP-{req_num:03d} | Specific impulse | "
                f"{isp:.0f} s | Propulsion spec |"
            )
            req_num += 1
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Small utility functions
# ---------------------------------------------------------------------------


def _friendly_analyzer(analyzer_id: str) -> str:
    """Map analyzer id to display name."""
    mapping: dict[str, str] = {
        "mass_budget": "Mass Budget",
        "power_budget": "Power Budget",
        "pin_voltage_check": "Pin Voltage Check",
        "thermal_node_model": "Thermal Analysis",
        "thermal_checker": "Thermal Limits",
    }
    return mapping.get(analyzer_id, analyzer_id)


def _analysis_detail_brief(result: AnalysisResult) -> str:
    """Build a short human-readable detail string from a result."""
    s = result.summary
    analyzer = result.analyzer

    if s.get("skipped"):
        reason = str(s.get("reason", "unknown"))[:40]
        return f"Skipped: {reason}"

    if analyzer == "mass_budget":
        total = s.get("total_mass", 0.0)
        budget = s.get("budget", 0.0)
        pct = (total / budget * 100) if budget > 0 else 0.0
        return f"{total:.2f} kg / {budget:.1f} kg ({pct:.1f}%)"

    if analyzer == "power_budget":
        consumption = s.get("total_consumption_w", 0.0)
        avg_gen = s.get("avg_generation_w", 0.0)
        return f"{consumption:.1f} W consumed / {avg_gen:.1f} W avg generation"

    if analyzer == "pin_voltage_check":
        total = s.get("total_connections", 0)
        ok = s.get("ok_connections", 0)
        return f"{ok}/{total} connections OK"

    if analyzer == "thermal_node_model":
        t_min = s.get("min_temp")
        t_max = s.get("max_temp")
        if t_min is not None and t_max is not None:
            return f"{t_min:.0f} C to {t_max:.0f} C"
        count = s.get("node_count", 0)
        return f"{count} nodes" if count else "No thermal data"

    if analyzer == "thermal_checker":
        checked = s.get("nodes_checked", 0)
        errors = s.get("errors", 0)
        warnings = s.get("warnings", 0)
        if errors == 0 and warnings == 0:
            return f"All {checked} nodes within limits"
        return f"{checked} nodes, {errors} errors, {warnings} warnings"

    return str(s)[:50]


def _get_component_property(
    design: CubeSatDesign, component_id: str, prop_name: str
) -> Any:
    """Look up a specific property from the component catalog for the design."""
    for comp in design.get_all_components():
        if comp["id"] == component_id:
            return comp.get("properties", {}).get(prop_name)
    return None


def _functional_tests_for(subsystem_id: str) -> list[tuple[str, str]]:
    """Return functional test names and pass criteria for a subsystem."""
    tests: dict[str, list[tuple[str, str]]] = {
        "eps": [
            ("Battery charge/discharge cycle", "Capacity within 5% of spec"),
            ("Solar MPPT tracking", "Efficiency > 90%"),
            ("Over-current protection", "Trips at rated limit"),
            ("Voltage regulation", "All rails within 3% tolerance"),
        ],
        "obc": [
            ("Boot sequence", "Boots within 30s, all services up"),
            ("Watchdog reset", "Recovers within 5s of watchdog timeout"),
            ("Memory read/write", "Zero bit errors after 1M cycles"),
            ("Telemetry generation", "All housekeeping parameters valid"),
        ],
        "com_uhf": [
            ("TX power output", "Within 1 dB of nominal"),
            ("RX sensitivity", "BER < 1e-5 at spec sensitivity"),
            ("Beacon transmission", "Correct AX.25 frame format"),
            ("Telecommand reception", "All command types acknowledged"),
        ],
        "com_sband": [
            ("TX power output", "Within 1 dB of nominal"),
            ("Data rate validation", "Sustained throughput meets spec"),
            ("Modulation quality", "EVM within spec"),
        ],
        "adcs": [
            ("Magnetorquer actuation", "Dipole moment within 5% of spec"),
            ("Reaction wheel spin-up", "Target RPM reached within 60s"),
            ("Sun sensor calibration", "Angle error < 2 deg"),
            ("Detumbling algorithm", "Angular rate < 1 deg/s in simulation"),
        ],
        "gps": [
            ("Cold start acquisition", "Fix within 120s (open sky)"),
            ("Position accuracy", "CEP < 10m"),
        ],
        "propulsion": [
            ("Valve actuation", "Opens and closes within spec time"),
            ("Leak test", "No measurable pressure drop in 24h"),
            ("Thrust measurement", "Within 10% of nominal"),
        ],
        "thermal": [
            ("Heater activation", "Temperature rise rate matches model"),
            ("Thermostat setpoint", "Activates within 2 C of setpoint"),
        ],
    }
    return tests.get(subsystem_id, [])


def _build_recommendations(
    design: CubeSatDesign,
    results: list[AnalysisResult],
) -> list[str]:
    """Build design recommendations based on analysis results and design choices."""
    recs: list[str] = []

    mass_margin = _mass_margin_pct(design)
    if mass_margin < 20:
        recs.append(
            f"Mass margin is {mass_margin:.1f}%, below the 20% recommended at PDR. "
            f"Consider removing non-essential components or selecting lighter alternatives."
        )
    elif mass_margin > 60:
        recs.append(
            f"Mass margin is {mass_margin:.1f}%. Consider upgrading to a smaller "
            f"form factor or adding redundancy."
        )

    power_result = _find_result(results, "power_budget")
    if power_result and power_result.status != AnalysisStatus.PASS:
        recs.append(
            "Power budget has warnings. Consider upgrading solar panels to "
            "deployable configuration or reducing payload duty cycle."
        )

    if design.solar_config == "Body-mounted" and design.sat_size in ("3U", "6U", "12U"):
        recs.append(
            "Body-mounted solar panels on a larger satellite may limit power generation. "
            "Consider deployable solar panels for improved power budget."
        )

    if design.orbit_altitude > 600 and "propulsion" not in design.subsystems:
        recs.append(
            f"Orbit altitude ({design.orbit_altitude:.0f} km) may not allow passive "
            f"deorbit within 25 years. Consider adding a propulsion system or drag sail."
        )

    if design.data_budget > 500 and "com_sband" not in design.subsystems:
        recs.append(
            f"Daily data budget of {design.data_budget:.0f} MB may be difficult to "
            f"downlink via UHF only. Consider adding S-Band downlink."
        )

    pin_result = _find_result(results, "pin_voltage_check")
    if pin_result and pin_result.status == AnalysisStatus.FAIL:
        recs.append(
            "Pin voltage mismatches detected. Review electrical interface "
            "specifications and add level shifters where needed."
        )

    thermal_result = _find_result(results, "thermal_checker")
    if thermal_result and thermal_result.status != AnalysisStatus.PASS:
        if "thermal" not in design.subsystems:
            recs.append(
                "Thermal analysis shows issues but no active thermal control is selected. "
                "Consider adding heaters or improving passive thermal design."
            )

    for r in results:
        if r.summary.get("skipped"):
            recs.append(
                f"{_friendly_analyzer(r.analyzer)} could not run. "
                f"Ensure the analysis environment is properly configured."
            )

    return recs


def _build_action_items(
    design: CubeSatDesign,
    results: list[AnalysisResult],
) -> list[tuple[str, str]]:
    """Build prioritized action items from analysis results."""
    items: list[tuple[str, str]] = []

    for r in results:
        for v in r.violations:
            if v.severity == Severity.ERROR:
                items.append((
                    f"Resolve {_friendly_analyzer(r.analyzer)} error: {v.message[:80]}",
                    "HIGH",
                ))
            elif v.severity == Severity.WARNING:
                items.append((
                    f"Address {_friendly_analyzer(r.analyzer)} warning: {v.message[:80]}",
                    "MEDIUM",
                ))

    # Design-level items
    if _mass_margin_pct(design) < 20:
        items.append(("Improve mass margin to >= 20%", "HIGH"))

    if design.orbit_altitude > 600 and "propulsion" not in design.subsystems:
        items.append(("Assess deorbit compliance (25-year rule)", "HIGH"))

    return items


# ---------------------------------------------------------------------------
# Main generator class
# ---------------------------------------------------------------------------


class ProjectDocGenerator:
    """Generate project management and documentation files for a CubeSat design.

    Produces five markdown documents that reflect the actual design configuration,
    selected subsystems, and analysis results.

    Args:
        design: The CubeSat design produced by the wizard.
        analysis_results: Optional list of analysis results from AutoAnalysisRunner.
    """

    def __init__(
        self,
        design: CubeSatDesign,
        analysis_results: list[AnalysisResult] | None = None,
    ) -> None:
        self._design = design
        self._results: list[AnalysisResult] = analysis_results or []

    def generate(self, output_dir: Path) -> DocsResult:
        """Generate all documentation files into *output_dir*.

        Creates the output directory if it does not exist.  Existing files
        with the same names are overwritten.

        Args:
            output_dir: Directory where markdown files will be written.

        Returns:
            A ``DocsResult`` with the list of generated file paths and the
            tracker file path.

        Raises:
            OSError: If the output directory cannot be created or files
                cannot be written.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        generators: list[tuple[str, str]] = [
            ("project_tracker.md", _generate_project_tracker(self._design, self._results)),
            ("timeline.md", _generate_timeline(self._design)),
            ("design_review.md", _generate_design_review(self._design, self._results)),
            ("test_plan.md", _generate_test_plan(self._design)),
            ("requirements.md", _generate_requirements(self._design)),
        ]

        generated_files: list[str] = []
        tracker_path = ""

        for filename, content in generators:
            filepath = output_dir / filename
            filepath.write_text(content, encoding="utf-8")
            generated_files.append(str(filepath))
            if filename == "project_tracker.md":
                tracker_path = str(filepath)

        return DocsResult(files=generated_files, tracker_file=tracker_path)
