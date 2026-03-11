"""Seed default ECSS rules into Neo4j knowledge graph."""
from __future__ import annotations

import logging

from ..core.graph_models import EcssRule, Severity
from ..core.graph_ops import GraphOperations

logger = logging.getLogger(__name__)

# Default ECSS-E-ST-20C electrical design rules
DEFAULT_ECSS_RULES: list[EcssRule] = [
    # --- Connector derating rules ---
    EcssRule(
        id="ECSS-E-ST-20C-5.3.1",
        standard="ECSS-E-ST-20C",
        clause="5.3.1",
        severity=Severity.ERROR,
        category="connector",
        check_expression="connector.current_rating * 0.75 >= connector.actual_current",
        message_template="Connector {name} exceeds 75% derating limit",
    ),
    EcssRule(
        id="ECSS-E-ST-20C-5.3.2",
        standard="ECSS-E-ST-20C",
        clause="5.3.2",
        severity=Severity.ERROR,
        category="connector",
        check_expression="connector.current_rating * 0.50 >= connector.actual_current",
        message_template="Connector {name} exceeds 50% derating for unmated cycles >500",
    ),
    # --- Wire/trace derating rules ---
    EcssRule(
        id="ECSS-E-ST-20C-5.4.1",
        standard="ECSS-E-ST-20C",
        clause="5.4.1",
        severity=Severity.ERROR,
        category="wire",
        check_expression="pin.current_max * 0.80 >= pin.actual_current",
        message_template="Wire to {name} exceeds 80% current derating",
    ),
    EcssRule(
        id="ECSS-E-ST-20C-5.4.2",
        standard="ECSS-E-ST-20C",
        clause="5.4.2",
        severity=Severity.WARNING,
        category="wire",
        check_expression="pin.current_max * 0.60 >= pin.actual_current",
        message_template="Wire to {name}: consider 60% derating for bundled harness",
    ),
    # --- Power margin rules ---
    EcssRule(
        id="ECSS-E-ST-20C-4.2.1",
        standard="ECSS-E-ST-20C",
        clause="4.2.1",
        severity=Severity.WARNING,
        category="power",
        check_expression="pin.current_max * 0.80 >= pin.actual_current",
        message_template="Power rail {name}: margin below 20% recommended minimum",
    ),
    EcssRule(
        id="ECSS-E-ST-20C-4.2.2",
        standard="ECSS-E-ST-20C",
        clause="4.2.2",
        severity=Severity.ERROR,
        category="power",
        check_expression="pin.current_max * 0.90 >= pin.actual_current",
        message_template="Power rail {name}: margin below 10% - critical",
    ),
    EcssRule(
        id="ECSS-E-ST-20C-4.2.3",
        standard="ECSS-E-ST-20C",
        clause="4.2.3",
        severity=Severity.INFO,
        category="power",
        check_expression="pin.current_max * 0.70 >= pin.actual_current",
        message_template="Power rail {name}: 30%+ margin recommended for EOL",
    ),
    # --- Grounding rules ---
    EcssRule(
        id="ECSS-E-ST-20C-5.5.1",
        standard="ECSS-E-ST-20C",
        clause="5.5.1",
        severity=Severity.ERROR,
        category="grounding",
        check_expression="pin.voltage == 0",
        message_template="Ground pin {name} has non-zero voltage: potential ground fault",
    ),
    EcssRule(
        id="ECSS-E-ST-20C-5.5.2",
        standard="ECSS-E-ST-20C",
        clause="5.5.2",
        severity=Severity.WARNING,
        category="grounding",
        check_expression="pin.current_max * 0.50 >= pin.actual_current",
        message_template="Ground return {name}: current exceeds 50% capacity",
    ),
    # --- EMC rules ---
    EcssRule(
        id="ECSS-E-ST-20C-5.7.1",
        standard="ECSS-E-ST-20C",
        clause="5.7.1",
        severity=Severity.WARNING,
        category="emc",
        check_expression="pin.voltage <= 50",
        message_template="Signal {name}: voltage exceeds 50V EMC threshold",
    ),
    EcssRule(
        id="ECSS-E-ST-20C-5.7.2",
        standard="ECSS-E-ST-20C",
        clause="5.7.2",
        severity=Severity.INFO,
        category="emc",
        check_expression="pin.current_max <= 5",
        message_template="Signal {name}: high current may cause EMI issues",
    ),
    # --- Voltage protection rules ---
    EcssRule(
        id="ECSS-E-ST-20C-5.2.1",
        standard="ECSS-E-ST-20C",
        clause="5.2.1",
        severity=Severity.ERROR,
        category="voltage",
        check_expression="pin.voltage <= pin.current_max * 100",
        message_template="Component {name}: voltage/current ratio check failed",
    ),
    # --- Redundancy rules ---
    EcssRule(
        id="ECSS-E-ST-20C-4.5.1",
        standard="ECSS-E-ST-20C",
        clause="4.5.1",
        severity=Severity.WARNING,
        category="redundancy",
        check_expression="pin.current_max > 0",
        message_template="Component {name}: single point of failure - consider redundancy",
    ),
    # --- Temperature derating ---
    EcssRule(
        id="ECSS-E-ST-20C-5.6.1",
        standard="ECSS-E-ST-20C",
        clause="5.6.1",
        severity=Severity.WARNING,
        category="thermal",
        check_expression="pin.current_max * 0.70 >= pin.actual_current",
        message_template="Component {name}: thermal derating margin insufficient at 70%",
    ),
    EcssRule(
        id="ECSS-E-ST-20C-5.6.2",
        standard="ECSS-E-ST-20C",
        clause="5.6.2",
        severity=Severity.ERROR,
        category="thermal",
        check_expression="pin.current_max * 0.85 >= pin.actual_current",
        message_template="Component {name}: exceeds 85% thermal derating limit",
    ),
]

# ECSS-E-ST-32C Structural design rules
ECSS_STRUCTURAL_RULES: list[EcssRule] = [
    # --- Mass budget rules ---
    EcssRule(
        id="ECSS-E-ST-32C-5.2.1",
        standard="ECSS-E-ST-32C",
        clause="5.2.1",
        severity=Severity.ERROR,
        category="mass",
        check_expression="structure.mass <= assembly.total_mass * (1 - config.mass_margin)",
        message_template="Structure {name} mass exceeds allocated budget minus margin",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-5.2.2",
        standard="ECSS-E-ST-32C",
        clause="5.2.2",
        severity=Severity.WARNING,
        category="mass",
        check_expression="assembly.total_mass * 0.95 >= sum(structure.mass)",
        message_template="Assembly {name}: mass margin below 5% - review budget",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-5.2.3",
        standard="ECSS-E-ST-32C",
        clause="5.2.3",
        severity=Severity.INFO,
        category="mass",
        check_expression="assembly.total_mass * 0.80 >= sum(structure.mass)",
        message_template="Assembly {name}: mass margin above 20% - nominal",
    ),
    # --- Structural safety factor rules ---
    EcssRule(
        id="ECSS-E-ST-32C-6.2.1",
        standard="ECSS-E-ST-32C",
        clause="6.2.1",
        severity=Severity.ERROR,
        category="structural_strength",
        check_expression="fem_result.safety_factor >= 1.25",
        message_template="Structure {name}: yield safety factor {sf} below 1.25 minimum",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-6.2.2",
        standard="ECSS-E-ST-32C",
        clause="6.2.2",
        severity=Severity.ERROR,
        category="structural_strength",
        check_expression="fem_result.safety_factor >= 1.50",
        message_template="Structure {name}: ultimate safety factor {sf} below 1.50 minimum",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-6.2.3",
        standard="ECSS-E-ST-32C",
        clause="6.2.3",
        severity=Severity.WARNING,
        category="structural_strength",
        check_expression="fem_result.safety_factor >= 2.0",
        message_template="Structure {name}: safety factor below 2.0 recommended for qualification",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-6.2.4",
        standard="ECSS-E-ST-32C",
        clause="6.2.4",
        severity=Severity.ERROR,
        category="structural_strength",
        check_expression="fem_result.max_stress <= material.yield_strength / 1.25",
        message_template="Structure {name}: max stress exceeds allowable yield stress",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-6.2.5",
        standard="ECSS-E-ST-32C",
        clause="6.2.5",
        severity=Severity.ERROR,
        category="structural_strength",
        check_expression="fem_result.max_stress <= material.ultimate_strength / 1.50",
        message_template="Structure {name}: max stress exceeds allowable ultimate stress",
    ),
    # --- Stiffness rules ---
    EcssRule(
        id="ECSS-E-ST-32C-6.3.1",
        standard="ECSS-E-ST-32C",
        clause="6.3.1",
        severity=Severity.ERROR,
        category="stiffness",
        check_expression="fem_result.frequencies[0] >= config.min_lateral_freq",
        message_template="Structure {name}: first lateral frequency {freq} Hz below {limit} Hz minimum",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-6.3.2",
        standard="ECSS-E-ST-32C",
        clause="6.3.2",
        severity=Severity.ERROR,
        category="stiffness",
        check_expression="fem_result.frequencies[0] >= config.min_axial_freq",
        message_template="Structure {name}: first axial frequency {freq} Hz below {limit} Hz minimum",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-6.3.3",
        standard="ECSS-E-ST-32C",
        clause="6.3.3",
        severity=Severity.WARNING,
        category="stiffness",
        check_expression="fem_result.max_displacement <= 0.001",
        message_template="Structure {name}: displacement {disp} m exceeds 1 mm quasi-static limit",
    ),
    # --- Assembly / CoG rules ---
    EcssRule(
        id="ECSS-E-ST-32C-5.3.1",
        standard="ECSS-E-ST-32C",
        clause="5.3.1",
        severity=Severity.ERROR,
        category="assembly",
        check_expression="assembly.level >= 0",
        message_template="Assembly {name}: invalid assembly level",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-5.3.2",
        standard="ECSS-E-ST-32C",
        clause="5.3.2",
        severity=Severity.WARNING,
        category="assembly",
        check_expression="abs(assembly.cog_x) <= 0.05 and abs(assembly.cog_y) <= 0.05",
        message_template="Assembly {name}: CoG offset exceeds 50 mm from geometric center",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-5.3.3",
        standard="ECSS-E-ST-32C",
        clause="5.3.3",
        severity=Severity.ERROR,
        category="assembly",
        check_expression="abs(assembly.cog_x) <= 0.10 and abs(assembly.cog_y) <= 0.10",
        message_template="Assembly {name}: CoG offset exceeds 100 mm - launcher constraint violated",
    ),
    # --- FEM quality rules ---
    EcssRule(
        id="ECSS-E-ST-32C-7.1.1",
        standard="ECSS-E-ST-32C",
        clause="7.1.1",
        severity=Severity.WARNING,
        category="fem_quality",
        check_expression="fem_model.element_count >= 1000",
        message_template="FEM model {name}: element count {count} may be too coarse",
    ),
    EcssRule(
        id="ECSS-E-ST-32C-7.1.2",
        standard="ECSS-E-ST-32C",
        clause="7.1.2",
        severity=Severity.ERROR,
        category="fem_quality",
        check_expression="mesh_quality.min_quality >= 0.3",
        message_template="FEM model {name}: minimum element quality {qual} below 0.3 threshold",
    ),
]

# ECSS-E-ST-31C Thermal control rules
ECSS_THERMAL_RULES: list[EcssRule] = [
    # --- Temperature limit rules ---
    EcssRule(
        id="ECSS-E-ST-31C-4.5.1",
        standard="ECSS-E-ST-31C",
        clause="4.5.1",
        severity=Severity.ERROR,
        category="thermal_limit",
        check_expression="thermal_node.temperature <= thermal_node.op_max_temp",
        message_template="Node {name}: temperature {temp} C exceeds max operational {limit} C",
    ),
    EcssRule(
        id="ECSS-E-ST-31C-4.5.2",
        standard="ECSS-E-ST-31C",
        clause="4.5.2",
        severity=Severity.ERROR,
        category="thermal_limit",
        check_expression="thermal_node.temperature >= thermal_node.op_min_temp",
        message_template="Node {name}: temperature {temp} C below min operational {limit} C",
    ),
    EcssRule(
        id="ECSS-E-ST-31C-4.5.3",
        standard="ECSS-E-ST-31C",
        clause="4.5.3",
        severity=Severity.WARNING,
        category="thermal_limit",
        check_expression="thermal_node.temperature <= thermal_node.op_max_temp - 10",
        message_template="Node {name}: temperature within 10 C of max operational limit",
    ),
    EcssRule(
        id="ECSS-E-ST-31C-4.5.4",
        standard="ECSS-E-ST-31C",
        clause="4.5.4",
        severity=Severity.WARNING,
        category="thermal_limit",
        check_expression="thermal_node.temperature >= thermal_node.op_min_temp + 10",
        message_template="Node {name}: temperature within 10 C of min operational limit",
    ),
    # --- Thermal gradient rules ---
    EcssRule(
        id="ECSS-E-ST-31C-5.2.1",
        standard="ECSS-E-ST-31C",
        clause="5.2.1",
        severity=Severity.WARNING,
        category="thermal_gradient",
        check_expression="abs(node_a.temperature - node_b.temperature) <= 40",
        message_template="Thermal gradient between {node_a} and {node_b} exceeds 40 C",
    ),
    EcssRule(
        id="ECSS-E-ST-31C-5.2.2",
        standard="ECSS-E-ST-31C",
        clause="5.2.2",
        severity=Severity.ERROR,
        category="thermal_gradient",
        check_expression="abs(node_a.temperature - node_b.temperature) <= 80",
        message_template="Thermal gradient between {node_a} and {node_b} exceeds 80 C - structural risk",
    ),
    # --- Thermal model completeness ---
    EcssRule(
        id="ECSS-E-ST-31C-5.3.1",
        standard="ECSS-E-ST-31C",
        clause="5.3.1",
        severity=Severity.ERROR,
        category="thermal_model",
        check_expression="thermal_node.capacity > 0",
        message_template="Node {name}: zero thermal capacity - invalid model",
    ),
    EcssRule(
        id="ECSS-E-ST-31C-5.3.2",
        standard="ECSS-E-ST-31C",
        clause="5.3.2",
        severity=Severity.WARNING,
        category="thermal_model",
        check_expression="conductance.value > 0",
        message_template="Conductance {name}: zero value - check model connectivity",
    ),
    # --- Power dissipation rules ---
    EcssRule(
        id="ECSS-E-ST-31C-4.3.1",
        standard="ECSS-E-ST-31C",
        clause="4.3.1",
        severity=Severity.WARNING,
        category="thermal_power",
        check_expression="thermal_node.power_dissipation >= 0",
        message_template="Node {name}: negative power dissipation - check model",
    ),
    EcssRule(
        id="ECSS-E-ST-31C-4.3.2",
        standard="ECSS-E-ST-31C",
        clause="4.3.2",
        severity=Severity.INFO,
        category="thermal_power",
        check_expression="thermal_node.power_dissipation <= 50",
        message_template="Node {name}: high power dissipation {power} W - verify heatsinking",
    ),
    # --- Orbital thermal cycle ---
    EcssRule(
        id="ECSS-E-ST-31C-6.1.1",
        standard="ECSS-E-ST-31C",
        clause="6.1.1",
        severity=Severity.ERROR,
        category="thermal_cycle",
        check_expression="hot_case.max_temp <= thermal_node.op_max_temp",
        message_template="Node {name}: hot case {temp} C exceeds operational max",
    ),
    EcssRule(
        id="ECSS-E-ST-31C-6.1.2",
        standard="ECSS-E-ST-31C",
        clause="6.1.2",
        severity=Severity.ERROR,
        category="thermal_cycle",
        check_expression="cold_case.min_temp >= thermal_node.op_min_temp",
        message_template="Node {name}: cold case {temp} C below operational min",
    ),
]

# ECSS-E-ST-33C Mechanism rules
ECSS_MECHANISM_RULES: list[EcssRule] = [
    # --- Deployment sequence rules ---
    EcssRule(
        id="ECSS-E-ST-33C-5.2.1",
        standard="ECSS-E-ST-33C",
        clause="5.2.1",
        severity=Severity.ERROR,
        category="deployment",
        check_expression="mechanism.state in ('stowed', 'deploying', 'deployed')",
        message_template="Mechanism {name}: invalid state '{state}'",
    ),
    EcssRule(
        id="ECSS-E-ST-33C-5.2.2",
        standard="ECSS-E-ST-33C",
        clause="5.2.2",
        severity=Severity.ERROR,
        category="deployment",
        check_expression="joint.torque >= joint.friction_torque * 2.0",
        message_template="Joint {name}: torque margin below 2x friction - deployment risk",
    ),
    EcssRule(
        id="ECSS-E-ST-33C-5.2.3",
        standard="ECSS-E-ST-33C",
        clause="5.2.3",
        severity=Severity.WARNING,
        category="deployment",
        check_expression="joint.torque >= joint.friction_torque * 3.0",
        message_template="Joint {name}: torque margin below 3x friction - recommended minimum",
    ),
    # --- Joint range rules ---
    EcssRule(
        id="ECSS-E-ST-33C-5.3.1",
        standard="ECSS-E-ST-33C",
        clause="5.3.1",
        severity=Severity.ERROR,
        category="joint",
        check_expression="joint.max_angle > joint.min_angle",
        message_template="Joint {name}: max angle must exceed min angle",
    ),
    EcssRule(
        id="ECSS-E-ST-33C-5.3.2",
        standard="ECSS-E-ST-33C",
        clause="5.3.2",
        severity=Severity.WARNING,
        category="joint",
        check_expression="joint.max_angle - joint.min_angle >= 5.0",
        message_template="Joint {name}: angular range below 5 degrees - verify clearance",
    ),
    EcssRule(
        id="ECSS-E-ST-33C-5.3.3",
        standard="ECSS-E-ST-33C",
        clause="5.3.3",
        severity=Severity.ERROR,
        category="joint",
        check_expression="joint.torque > 0",
        message_template="Joint {name}: zero available torque",
    ),
    # --- Mechanism lifecycle rules ---
    EcssRule(
        id="ECSS-E-ST-33C-6.1.1",
        standard="ECSS-E-ST-33C",
        clause="6.1.1",
        severity=Severity.WARNING,
        category="mechanism_life",
        check_expression="mechanism.dof >= 1",
        message_template="Mechanism {name}: zero degrees of freedom",
    ),
    EcssRule(
        id="ECSS-E-ST-33C-6.1.2",
        standard="ECSS-E-ST-33C",
        clause="6.1.2",
        severity=Severity.ERROR,
        category="mechanism_life",
        check_expression="joint.friction_torque < joint.torque",
        message_template="Mechanism {name}: friction exceeds available torque - will not deploy",
    ),
    EcssRule(
        id="ECSS-E-ST-33C-6.2.1",
        standard="ECSS-E-ST-33C",
        clause="6.2.1",
        severity=Severity.WARNING,
        category="mechanism_life",
        check_expression="mechanism.type != 'SPRING' or joint.torque >= joint.friction_torque * 4.0",
        message_template="Spring mechanism {name}: torque margin below 4x for one-shot deployment",
    ),
]

# ECSS-E-HB-32-26A Vibration and shock rules
ECSS_VIBRATION_RULES: list[EcssRule] = [
    # --- Modal analysis rules ---
    EcssRule(
        id="ECSS-E-HB-32-26A-4.1.1",
        standard="ECSS-E-HB-32-26A",
        clause="4.1.1",
        severity=Severity.ERROR,
        category="modal",
        check_expression="fem_result.frequencies[0] >= config.min_lateral_freq",
        message_template="First lateral mode {freq} Hz below {limit} Hz requirement",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-4.1.2",
        standard="ECSS-E-HB-32-26A",
        clause="4.1.2",
        severity=Severity.ERROR,
        category="modal",
        check_expression="fem_result.frequencies[0] >= config.min_axial_freq",
        message_template="First axial mode {freq} Hz below {limit} Hz requirement",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-4.1.3",
        standard="ECSS-E-HB-32-26A",
        clause="4.1.3",
        severity=Severity.WARNING,
        category="modal",
        check_expression="len(fem_result.frequencies) >= 10",
        message_template="Modal analysis: fewer than 10 modes extracted - may be insufficient",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-4.1.4",
        standard="ECSS-E-HB-32-26A",
        clause="4.1.4",
        severity=Severity.WARNING,
        category="modal",
        check_expression="fem_result.frequencies[-1] >= 2000",
        message_template="Modal analysis: highest mode below 2000 Hz - extend frequency range",
    ),
    # --- Random vibration rules ---
    EcssRule(
        id="ECSS-E-HB-32-26A-5.1.1",
        standard="ECSS-E-HB-32-26A",
        clause="5.1.1",
        severity=Severity.ERROR,
        category="random_vib",
        check_expression="load_case.magnitude <= 20.0",
        message_template="Random vibration {name}: {mag} gRMS exceeds 20 gRMS qualification level",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-5.1.2",
        standard="ECSS-E-HB-32-26A",
        clause="5.1.2",
        severity=Severity.WARNING,
        category="random_vib",
        check_expression="load_case.magnitude <= 14.0",
        message_template="Random vibration {name}: {mag} gRMS exceeds 14 gRMS acceptance level",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-5.1.3",
        standard="ECSS-E-HB-32-26A",
        clause="5.1.3",
        severity=Severity.ERROR,
        category="random_vib",
        check_expression="load_case.duration >= 120",
        message_template="Random vibration {name}: duration {dur}s below 120s minimum",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-5.1.4",
        standard="ECSS-E-HB-32-26A",
        clause="5.1.4",
        severity=Severity.WARNING,
        category="random_vib",
        check_expression="len(load_case.psd_profile) >= 5",
        message_template="Random vibration {name}: PSD profile has fewer than 5 breakpoints",
    ),
    # --- Shock rules ---
    EcssRule(
        id="ECSS-E-HB-32-26A-6.1.1",
        standard="ECSS-E-HB-32-26A",
        clause="6.1.1",
        severity=Severity.ERROR,
        category="shock",
        check_expression="load_case.magnitude <= 5000",
        message_template="Shock {name}: SRS {mag} g exceeds 5000 g equipment limit",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-6.1.2",
        standard="ECSS-E-HB-32-26A",
        clause="6.1.2",
        severity=Severity.WARNING,
        category="shock",
        check_expression="load_case.magnitude <= 2000",
        message_template="Shock {name}: SRS {mag} g exceeds 2000 g - verify component qualification",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-6.1.3",
        standard="ECSS-E-HB-32-26A",
        clause="6.1.3",
        severity=Severity.INFO,
        category="shock",
        check_expression="load_case.type == 'SHOCK'",
        message_template="Shock analysis {name}: verify SRS meets launcher ICD requirements",
    ),
    # --- Sine vibration rules ---
    EcssRule(
        id="ECSS-E-HB-32-26A-4.3.1",
        standard="ECSS-E-HB-32-26A",
        clause="4.3.1",
        severity=Severity.ERROR,
        category="sine_vib",
        check_expression="load_case.magnitude <= 30.0",
        message_template="Sine vibration {name}: {mag} g exceeds 30 g qualification level",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-4.3.2",
        standard="ECSS-E-HB-32-26A",
        clause="4.3.2",
        severity=Severity.WARNING,
        category="sine_vib",
        check_expression="load_case.magnitude <= 20.0",
        message_template="Sine vibration {name}: {mag} g exceeds 20 g acceptance level",
    ),
    # --- Quasi-static rules ---
    EcssRule(
        id="ECSS-E-HB-32-26A-4.2.1",
        standard="ECSS-E-HB-32-26A",
        clause="4.2.1",
        severity=Severity.ERROR,
        category="quasi_static",
        check_expression="fem_result.safety_factor >= 1.25",
        message_template="Quasi-static {name}: safety factor {sf} below 1.25 yield requirement",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-4.2.2",
        standard="ECSS-E-HB-32-26A",
        clause="4.2.2",
        severity=Severity.ERROR,
        category="quasi_static",
        check_expression="fem_result.safety_factor >= 1.50",
        message_template="Quasi-static {name}: safety factor {sf} below 1.50 ultimate requirement",
    ),
    EcssRule(
        id="ECSS-E-HB-32-26A-4.2.3",
        standard="ECSS-E-HB-32-26A",
        clause="4.2.3",
        severity=Severity.WARNING,
        category="quasi_static",
        check_expression="fem_result.max_displacement <= 0.002",
        message_template="Quasi-static {name}: displacement exceeds 2 mm allowable",
    ),
]

# Combined list of all mechanical rules
ECSS_MECHANICAL_RULES: list[EcssRule] = (
    ECSS_STRUCTURAL_RULES
    + ECSS_THERMAL_RULES
    + ECSS_MECHANISM_RULES
    + ECSS_VIBRATION_RULES
)

# Add mechanical rules to default set
DEFAULT_ECSS_RULES.extend(ECSS_MECHANICAL_RULES)


async def seed_default_rules(graph: GraphOperations) -> int:
    """Seed default ECSS rules into Neo4j if not already present.

    Returns the number of rules seeded.
    """
    existing = await graph.get_ecss_rules()
    existing_ids = {r.id for r in existing}

    new_rules = [r for r in DEFAULT_ECSS_RULES if r.id not in existing_ids]
    if not new_rules:
        logger.info("All %d default ECSS rules already present", len(DEFAULT_ECSS_RULES))
        return 0

    count = await graph.load_ecss_rules(new_rules)
    logger.info("Seeded %d new ECSS rules (total: %d)", count, len(DEFAULT_ECSS_RULES))
    return count
