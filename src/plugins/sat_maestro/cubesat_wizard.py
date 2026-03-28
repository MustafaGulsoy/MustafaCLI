"""CubeSat Design Wizard — interactive questionnaire and Neo4j seeding."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Design questionnaire definition
# ---------------------------------------------------------------------------

QUESTIONS = [
    {
        "id": "sat_size",
        "question": "Uydu boyutu nedir?",
        "options": ["1U", "2U", "3U", "6U", "12U"],
        "default": "1U",
        "help": "1U = 10x10x10cm, ~1.33kg max",
    },
    {
        "id": "mission_name",
        "question": "Misyon adi nedir?",
        "type": "text",
        "default": "MyCubeSat-1",
    },
    {
        "id": "orbit_type",
        "question": "Yörünge tipi nedir?",
        "options": ["LEO", "SSO", "MEO", "GTO"],
        "default": "LEO",
    },
    {
        "id": "orbit_altitude",
        "question": "Yörünge yüksekligi (km)?",
        "type": "number",
        "default": 500,
        "range": [200, 2000],
    },
    {
        "id": "orbit_inclination",
        "question": "Yörünge egimi (derece)?",
        "type": "number",
        "default": 97.4,
        "range": [0, 180],
        "help": "SSO icin ~97-98 derece",
    },
    {
        "id": "design_life",
        "question": "Tasarim ömrü (yil)?",
        "type": "number",
        "default": 2,
        "range": [0.5, 10],
    },
    {
        "id": "payload_type",
        "question": "Payload (faydalı yük) tipi nedir?",
        "options": [
            "Camera (EO)",
            "SDR (Comms)",
            "AIS Receiver",
            "IoT Gateway",
            "Science Instrument",
            "Technology Demo",
            "Custom",
        ],
        "default": "Camera (EO)",
    },
    {
        "id": "payload_power",
        "question": "Payload güç tüketimi (W)?",
        "type": "number",
        "default": 5.0,
        "range": [0.1, 50],
    },
    {
        "id": "payload_mass",
        "question": "Payload kütlesi (g)?",
        "type": "number",
        "default": 200,
        "range": [10, 5000],
    },
    {
        "id": "subsystems",
        "question": "Hangi alt sistemler olacak?",
        "type": "multi_select",
        "options": [
            {"id": "eps", "name": "EPS (Güç Sistemi)", "default": True},
            {"id": "obc", "name": "OBC (Bilgisayar)", "default": True},
            {"id": "com_uhf", "name": "UHF Haberlesme", "default": True},
            {"id": "com_sband", "name": "S-Band Haberlesme", "default": False},
            {"id": "adcs", "name": "ADCS (Yönelim Kontrolü)", "default": True},
            {"id": "gps", "name": "GPS Alici", "default": False},
            {"id": "propulsion", "name": "İtki Sistemi", "default": False},
            {"id": "thermal", "name": "Aktif Termal Kontrol", "default": False},
        ],
    },
    {
        "id": "solar_config",
        "question": "Günes paneli konfigürasyonu?",
        "options": ["Body-mounted", "Deployable 2-panel", "Deployable 4-panel"],
        "default": "Body-mounted",
    },
    {
        "id": "battery_type",
        "question": "Batarya tipi?",
        "options": ["Li-ion 18650", "Li-Po Pouch", "Li-ion Prismatic"],
        "default": "Li-ion 18650",
    },
    {
        "id": "data_budget",
        "question": "Günlük veri üretimi tahmini (MB)?",
        "type": "number",
        "default": 100,
        "range": [1, 10000],
    },
]


# ---------------------------------------------------------------------------
# Subsystem component catalog (typical COTS CubeSat components)
# ---------------------------------------------------------------------------

COMPONENT_CATALOG = {
    "eps": {
        "name": "EPS",
        "components": [
            {"id": "eps_pcu", "name": "PCU (Power Control Unit)", "type": "MODULE",
             "mass_g": 85, "power_w": 0.5, "voltage": 3.3,
             "properties": {"efficiency": 0.92, "max_input_v": 20, "mppt_channels": 4}},
            {"id": "eps_batt", "name": "Battery Pack", "type": "MODULE",
             "mass_g": 200, "power_w": 0, "voltage": 7.4,
             "properties": {"capacity_wh": 20, "cells": 4, "chemistry": "Li-ion"}},
            {"id": "eps_solar", "name": "Solar Panel Array", "type": "MODULE",
             "mass_g": 150, "power_w": -7.0, "voltage": 8.5,
             "properties": {"cell_type": "GaAs", "area_cm2": 300, "efficiency": 0.28}},
        ],
    },
    "obc": {
        "name": "OBC",
        "components": [
            {"id": "obc_main", "name": "On-Board Computer", "type": "MODULE",
             "mass_g": 50, "power_w": 0.4, "voltage": 3.3,
             "properties": {"cpu": "ARM Cortex-M7", "ram_mb": 512, "flash_gb": 8}},
        ],
    },
    "com_uhf": {
        "name": "UHF Communication",
        "components": [
            {"id": "com_uhf_trx", "name": "UHF Transceiver", "type": "MODULE",
             "mass_g": 75, "power_w": 2.0, "voltage": 5.0,
             "properties": {"freq_mhz": 437, "tx_power_dbm": 30, "data_rate_kbps": 9.6}},
            {"id": "com_uhf_ant", "name": "UHF Antenna (Deployable)", "type": "MODULE",
             "mass_g": 30, "power_w": 0, "voltage": 0,
             "properties": {"gain_dbi": 2.1, "type": "monopole", "deployable": True}},
        ],
    },
    "com_sband": {
        "name": "S-Band Communication",
        "components": [
            {"id": "com_sband_tx", "name": "S-Band Transmitter", "type": "MODULE",
             "mass_g": 90, "power_w": 6.0, "voltage": 5.0,
             "properties": {"freq_ghz": 2.4, "tx_power_dbm": 27, "data_rate_mbps": 2}},
            {"id": "com_sband_ant", "name": "S-Band Patch Antenna", "type": "MODULE",
             "mass_g": 20, "power_w": 0, "voltage": 0,
             "properties": {"gain_dbi": 7, "type": "patch"}},
        ],
    },
    "adcs": {
        "name": "ADCS",
        "components": [
            {"id": "adcs_unit", "name": "ADCS Unit", "type": "MODULE",
             "mass_g": 100, "power_w": 0.8, "voltage": 5.0,
             "properties": {"pointing_accuracy_deg": 1.0, "reaction_wheels": 3,
                            "magnetorquer": True, "sun_sensor": True, "gyro": True}},
        ],
    },
    "gps": {
        "name": "GPS",
        "components": [
            {"id": "gps_rx", "name": "GPS Receiver", "type": "MODULE",
             "mass_g": 25, "power_w": 0.3, "voltage": 3.3,
             "properties": {"channels": 12, "accuracy_m": 10}},
        ],
    },
    "propulsion": {
        "name": "Propulsion",
        "components": [
            {"id": "prop_unit", "name": "Cold Gas Thruster", "type": "MODULE",
             "mass_g": 300, "power_w": 1.0, "voltage": 5.0,
             "properties": {"delta_v_ms": 15, "isp_s": 65, "propellant": "R-236fa"}},
        ],
    },
    "thermal": {
        "name": "Active Thermal",
        "components": [
            {"id": "therm_heater", "name": "Heater Circuit", "type": "MODULE",
             "mass_g": 15, "power_w": 2.0, "voltage": 5.0,
             "properties": {"zones": 2, "thermostat": True}},
        ],
    },
}

# Size constraints per CubeSat form factor
SIZE_LIMITS = {
    "1U":  {"max_mass_kg": 1.33, "volume_cm3": 1000, "max_power_orbit_avg_w": 2.5},
    "2U":  {"max_mass_kg": 2.66, "volume_cm3": 2000, "max_power_orbit_avg_w": 5.0},
    "3U":  {"max_mass_kg": 4.00, "volume_cm3": 3000, "max_power_orbit_avg_w": 8.0},
    "6U":  {"max_mass_kg": 12.0, "volume_cm3": 6000, "max_power_orbit_avg_w": 20.0},
    "12U": {"max_mass_kg": 24.0, "volume_cm3": 12000, "max_power_orbit_avg_w": 40.0},
}


@dataclass
class CubeSatDesign:
    """Complete CubeSat design from wizard answers."""
    mission_name: str = "MyCubeSat-1"
    sat_size: str = "1U"
    orbit_type: str = "LEO"
    orbit_altitude: float = 500
    orbit_inclination: float = 97.4
    design_life: float = 2.0
    payload_type: str = "Camera (EO)"
    payload_power: float = 5.0
    payload_mass: float = 200
    subsystems: list[str] = field(default_factory=lambda: ["eps", "obc", "com_uhf", "adcs"])
    solar_config: str = "Body-mounted"
    battery_type: str = "Li-ion 18650"
    data_budget: float = 100

    @property
    def limits(self) -> dict:
        return SIZE_LIMITS.get(self.sat_size, SIZE_LIMITS["1U"])

    def get_all_components(self) -> list[dict]:
        """Get all components for selected subsystems + payload."""
        components = []
        for ss_id in self.subsystems:
            if ss_id in COMPONENT_CATALOG:
                for comp in COMPONENT_CATALOG[ss_id]["components"]:
                    components.append({**comp, "subsystem": COMPONENT_CATALOG[ss_id]["name"]})

        # Add payload as component
        components.append({
            "id": "payload_main",
            "name": f"Payload ({self.payload_type})",
            "type": "MODULE",
            "mass_g": self.payload_mass,
            "power_w": self.payload_power,
            "voltage": 5.0,
            "subsystem": "Payload",
            "properties": {"type": self.payload_type},
        })

        # Add structure
        struct_mass = {"1U": 100, "2U": 180, "3U": 250, "6U": 500, "12U": 900}
        components.append({
            "id": "structure_frame",
            "name": f"{self.sat_size} Structure Frame",
            "type": "MODULE",
            "mass_g": struct_mass.get(self.sat_size, 100),
            "power_w": 0,
            "voltage": 0,
            "subsystem": "Structure",
            "properties": {"material": "Al-7075", "form_factor": self.sat_size},
        })

        return components

    def total_mass_g(self) -> float:
        return sum(c["mass_g"] for c in self.get_all_components())

    def total_power_w(self) -> float:
        return sum(c["power_w"] for c in self.get_all_components() if c["power_w"] > 0)

    def to_summary(self) -> str:
        """Human-readable design summary."""
        comps = self.get_all_components()
        total_mass = self.total_mass_g()
        total_power = self.total_power_w()
        limits = self.limits
        mass_margin = ((limits["max_mass_kg"] * 1000) - total_mass) / (limits["max_mass_kg"] * 1000) * 100

        lines = [
            f"{'=' * 60}",
            f"  {self.mission_name} — {self.sat_size} CubeSat Design Summary",
            f"{'=' * 60}",
            f"",
            f"  Orbit: {self.orbit_type} {self.orbit_altitude:.0f}km, {self.orbit_inclination:.1f} deg",
            f"  Design Life: {self.design_life} years",
            f"  Payload: {self.payload_type} ({self.payload_power}W, {self.payload_mass}g)",
            f"",
            f"  {'Component':<35} {'Mass(g)':>8} {'Power(W)':>9} {'Subsystem':<15}",
            f"  {'-' * 67}",
        ]

        for c in comps:
            pwr = f"{c['power_w']:.1f}" if c['power_w'] != 0 else "-"
            lines.append(f"  {c['name']:<35} {c['mass_g']:>8.0f} {pwr:>9} {c['subsystem']:<15}")

        lines.extend([
            f"  {'-' * 67}",
            f"  {'TOTAL':<35} {total_mass:>8.0f} {total_power:>8.1f}W",
            f"",
            f"  Mass Limit: {limits['max_mass_kg'] * 1000:.0f}g | Used: {total_mass:.0f}g | Margin: {mass_margin:.1f}%",
            f"  Power Orbit Avg: {limits['max_power_orbit_avg_w']}W available",
            f"{'=' * 60}",
        ])
        return "\n".join(lines)


def get_questionnaire() -> str:
    """Return the full questionnaire as formatted text for the LLM to present."""
    lines = [
        "CubeSat Tasarim Sihirbazi",
        "=" * 40,
        "",
        "Asagidaki sorulari kullaniciya tek tek sorun ve cevaplari toplayin.",
        "Tum cevaplar toplandiktan sonra sat_cubesat_create tool'unu cagirin.",
        "",
    ]
    for i, q in enumerate(QUESTIONS, 1):
        lines.append(f"{i}. {q['question']}")
        if "options" in q and not isinstance(q.get("options", [{}])[0], dict):
            lines.append(f"   Secenekler: {', '.join(q['options'])}")
        elif q.get("type") == "multi_select":
            opts = [f"{o['name']} ({'varsayilan' if o['default'] else 'opsiyonel'})"
                    for o in q["options"]]
            lines.append(f"   Secenekler: {', '.join(opts)}")
        if "default" in q:
            lines.append(f"   Varsayilan: {q['default']}")
        if "help" in q:
            lines.append(f"   Not: {q['help']}")
        lines.append("")

    return "\n".join(lines)


def build_neo4j_cypher(design: CubeSatDesign) -> list[str]:
    """Generate Cypher statements to seed the CubeSat into Neo4j."""
    queries = []

    # Create mission node
    queries.append(
        f"MERGE (m:Mission {{name: '{design.mission_name}'}}) "
        f"SET m.size = '{design.sat_size}', "
        f"m.orbit_type = '{design.orbit_type}', "
        f"m.orbit_altitude_km = {design.orbit_altitude}, "
        f"m.orbit_inclination_deg = {design.orbit_inclination}, "
        f"m.design_life_years = {design.design_life}, "
        f"m.max_mass_kg = {design.limits['max_mass_kg']}, "
        f"m.payload_type = '{design.payload_type}'"
    )

    # Create components and relationships
    for comp in design.get_all_components():
        props_json = json.dumps(comp.get("properties", {})).replace("'", "\\'")
        queries.append(
            f"MERGE (c:Component {{id: '{comp['id']}'}}) "
            f"SET c.name = '{comp['name']}', "
            f"c.type = '{comp['type']}', "
            f"c.subsystem = '{comp['subsystem']}', "
            f"c.mass_g = {comp['mass_g']}, "
            f"c.power_w = {comp['power_w']}, "
            f"c.voltage = {comp.get('voltage', 0)}, "
            f"c.properties = '{props_json}'"
        )
        # Link to mission
        queries.append(
            f"MATCH (m:Mission {{name: '{design.mission_name}'}}), "
            f"(c:Component {{id: '{comp['id']}'}}) "
            f"MERGE (m)-[:HAS_COMPONENT]->(c)"
        )

    # Create Assembly node
    queries.append(
        f"MERGE (a:Assembly {{name: '{design.mission_name}_assembly'}}) "
        f"SET a.total_mass_g = {design.total_mass_g()}, "
        f"a.total_power_w = {design.total_power_w()}, "
        f"a.form_factor = '{design.sat_size}'"
    )

    return queries
