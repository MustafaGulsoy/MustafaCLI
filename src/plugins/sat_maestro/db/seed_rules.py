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
