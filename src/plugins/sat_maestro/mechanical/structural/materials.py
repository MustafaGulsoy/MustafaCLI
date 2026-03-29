"""Material property database for CubeSat structural analysis.

Provides material definitions (elastic modulus, Poisson ratio, density,
yield strength) and a mapping from component IDs in the COMPONENT_CATALOG
to their representative material.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Material:
    """Isotropic linear-elastic material definition.

    Args:
        name: Human-readable material identifier.
        youngs_modulus: Young's modulus in MPa.
        poisson_ratio: Poisson's ratio (dimensionless).
        density: Mass density in kg/m^3.
        yield_strength: 0.2 % offset yield strength in MPa.
        cte: Coefficient of thermal expansion in 1/K (optional).
        thermal_conductivity: Thermal conductivity in W/(m*K) (optional).
    """

    name: str
    youngs_modulus: float  # MPa
    poisson_ratio: float
    density: float  # kg/m^3
    yield_strength: float  # MPa
    cte: float = 0.0  # 1/K
    thermal_conductivity: float = 0.0  # W/(m*K)

    def shear_modulus(self) -> float:
        """Compute shear modulus G from E and nu."""
        return self.youngs_modulus / (2.0 * (1.0 + self.poisson_ratio))

    def bulk_modulus(self) -> float:
        """Compute bulk modulus K from E and nu."""
        return self.youngs_modulus / (3.0 * (1.0 - 2.0 * self.poisson_ratio))


# ---------------------------------------------------------------------------
# Material library
# ---------------------------------------------------------------------------

MATERIALS: dict[str, Material] = {
    # Structural metals
    "AL7075": Material(
        name="Aluminium 7075-T6",
        youngs_modulus=71_700.0,
        poisson_ratio=0.33,
        density=2_810.0,
        yield_strength=503.0,
        cte=23.6e-6,
        thermal_conductivity=130.0,
    ),
    "AL6061": Material(
        name="Aluminium 6061-T6",
        youngs_modulus=68_900.0,
        poisson_ratio=0.33,
        density=2_700.0,
        yield_strength=276.0,
        cte=23.6e-6,
        thermal_conductivity=167.0,
    ),
    "TI6AL4V": Material(
        name="Titanium Ti-6Al-4V",
        youngs_modulus=113_800.0,
        poisson_ratio=0.342,
        density=4_430.0,
        yield_strength=880.0,
        cte=8.6e-6,
        thermal_conductivity=6.7,
    ),
    "SS304": Material(
        name="Stainless Steel 304",
        youngs_modulus=193_000.0,
        poisson_ratio=0.29,
        density=8_000.0,
        yield_strength=215.0,
        cte=17.3e-6,
        thermal_conductivity=16.2,
    ),
    # PCB / electronics substrates
    "FR4": Material(
        name="FR-4 Glass Epoxy",
        youngs_modulus=22_000.0,
        poisson_ratio=0.12,
        density=1_850.0,
        yield_strength=300.0,
        cte=14.0e-6,
        thermal_conductivity=0.3,
    ),
    # Battery cells (effective homogenised properties)
    "BATTERY": Material(
        name="Li-ion Cell (Homogenised)",
        youngs_modulus=10_000.0,
        poisson_ratio=0.30,
        density=2_500.0,
        yield_strength=100.0,
        cte=10.0e-6,
        thermal_conductivity=3.0,
    ),
    # Solar cell stack (cover glass + GaAs + substrate)
    "SOLAR_CELL": Material(
        name="GaAs Solar Cell Stack",
        youngs_modulus=85_000.0,
        poisson_ratio=0.31,
        density=5_300.0,
        yield_strength=70.0,
        cte=5.7e-6,
        thermal_conductivity=55.0,
    ),
    # Cold-gas propellant tank (PEEK composite)
    "PEEK": Material(
        name="PEEK Composite",
        youngs_modulus=4_100.0,
        poisson_ratio=0.38,
        density=1_300.0,
        yield_strength=100.0,
        cte=47.0e-6,
        thermal_conductivity=0.25,
    ),
    # Generic electronics module (weighted average)
    "ELECTRONICS": Material(
        name="Generic Electronics Module",
        youngs_modulus=18_000.0,
        poisson_ratio=0.20,
        density=2_000.0,
        yield_strength=150.0,
        cte=12.0e-6,
        thermal_conductivity=1.0,
    ),
    # Antenna (FR4 + copper traces)
    "ANTENNA_PCB": Material(
        name="Antenna PCB (FR4 + Cu)",
        youngs_modulus=25_000.0,
        poisson_ratio=0.15,
        density=2_100.0,
        yield_strength=250.0,
        cte=13.0e-6,
        thermal_conductivity=1.5,
    ),
}


# ---------------------------------------------------------------------------
# Component ID -> material key mapping
# ---------------------------------------------------------------------------

COMPONENT_MATERIALS: dict[str, str] = {
    # Structure
    "structure_frame": "AL7075",
    # EPS
    "eps_pcu": "FR4",
    "eps_batt": "BATTERY",
    "eps_solar": "SOLAR_CELL",
    # OBC
    "obc_main": "FR4",
    # UHF comms
    "com_uhf_trx": "ELECTRONICS",
    "com_uhf_ant": "ANTENNA_PCB",
    # S-Band comms
    "com_sband_tx": "ELECTRONICS",
    "com_sband_ant": "ANTENNA_PCB",
    # ADCS
    "adcs_unit": "ELECTRONICS",
    # GPS
    "gps_rx": "FR4",
    # Propulsion
    "prop_unit": "PEEK",
    # Thermal
    "therm_heater": "FR4",
    # Payload (default, can be overridden)
    "payload_main": "FR4",
}

# Fallback material for any component ID not in the mapping above.
DEFAULT_MATERIAL_KEY = "ELECTRONICS"


def get_material_for_component(component_id: str) -> Material:
    """Look up the material for a given component ID.

    Falls back to DEFAULT_MATERIAL_KEY when *component_id* is not in the
    mapping table.

    Args:
        component_id: The ``id`` field from a COMPONENT_CATALOG entry.

    Returns:
        The resolved ``Material`` dataclass instance.
    """
    key = COMPONENT_MATERIALS.get(component_id, DEFAULT_MATERIAL_KEY)
    mat = MATERIALS.get(key)
    if mat is None:
        logger.warning(
            "Material key '%s' for component '%s' not found, "
            "falling back to '%s'",
            key,
            component_id,
            DEFAULT_MATERIAL_KEY,
        )
        mat = MATERIALS[DEFAULT_MATERIAL_KEY]
    return mat
