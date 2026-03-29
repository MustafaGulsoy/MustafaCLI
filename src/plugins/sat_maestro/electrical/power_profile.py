"""Orbital power profile analyzer for CubeSat missions.

Calculates power generation versus consumption over one orbital period,
accounting for eclipse/sunlit phases, subsystem duty cycles, solar panel
configuration, and battery depth-of-discharge constraints.  Produces a
time-resolved profile and a standard ``AnalysisResult`` for the pipeline.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..core.graph_models import (
    AnalysisResult,
    AnalysisStatus,
    Severity,
    Violation,
)
from ..cubesat_wizard import COMPONENT_CATALOG, CubeSatDesign, SIZE_LIMITS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
_EARTH_RADIUS_M: float = 6_371_000.0  # metres
_MU: float = 3.986004418e14  # m^3/s^2  (standard gravitational parameter)
_SECONDS_PER_MINUTE: float = 60.0
_SECONDS_PER_YEAR: float = 365.25 * 86400.0

# ---------------------------------------------------------------------------
# Solar panel configuration multipliers
# ---------------------------------------------------------------------------
_SOLAR_CONFIG_MULTIPLIER: dict[str, float] = {
    "Body-mounted": 1.0,
    "Deployable 2-panel": 2.0,
    "Deployable 4-panel": 4.0,
}

# ---------------------------------------------------------------------------
# Subsystem duty cycles (fraction of orbit time that subsystem is active)
# ---------------------------------------------------------------------------
_DEFAULT_DUTY_CYCLES: dict[str, float] = {
    "eps": 1.0,      # always on
    "obc": 1.0,      # always on
    "adcs": 1.0,     # always on
    "com_uhf": 0.10,  # 10% TX duty (beacon every ~60s, RX always on at low power)
    "com_sband": 0.05,  # ~10 min per orbit ground pass
    "gps": 0.50,     # periodic position fixes
    "propulsion": 0.01,  # very short burns
    "thermal": 0.30,  # thermostat-controlled heater
}

# UHF RX standby power fraction (RX consumes ~20% of TX power when listening)
_UHF_RX_DUTY: float = 1.0
_UHF_RX_POWER_FRACTION: float = 0.20

# ---------------------------------------------------------------------------
# Battery constraints
# ---------------------------------------------------------------------------
_MAX_DOD_PERCENT: float = 20.0  # recommended for Li-ion long life
_BATTERY_EFFICIENCY: float = 0.90  # round-trip charge/discharge
_EPS_EFFICIENCY: float = 0.92  # power conditioning loss

# ---------------------------------------------------------------------------
# Simulation resolution
# ---------------------------------------------------------------------------
_TIME_STEP_MINUTES: float = 0.5  # 30-second resolution


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PowerProfileResult:
    """Full-orbit power profile analysis result."""

    orbit_period_min: float
    eclipse_duration_min: float
    sunlit_duration_min: float
    solar_power_w: float  # peak generation (at panel output)
    avg_generation_w: float  # orbit-average after losses
    avg_consumption_w: float  # orbit-average with duty cycles
    peak_consumption_w: float  # all subsystems simultaneously
    battery_capacity_wh: float
    battery_depth_of_discharge: float  # percentage
    battery_cycles_per_year: int
    energy_balance_positive: bool
    duty_cycle_payload: float  # maximum payload duty cycle for balance
    margin_percent: float  # (gen - cons) / gen * 100
    profile_data: list[dict[str, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _orbit_period_seconds(altitude_km: float) -> float:
    """Kepler's third law: T = 2*pi*sqrt(a^3/mu).

    Args:
        altitude_km: Orbital altitude above Earth surface.

    Returns:
        Orbit period in seconds.
    """
    a = _EARTH_RADIUS_M + altitude_km * 1000.0
    return 2.0 * math.pi * math.sqrt(a ** 3 / _MU)


def _eclipse_fraction(altitude_km: float, beta_deg: float = 0.0) -> float:
    """Eclipse fraction for a circular orbit.

    f_eclipse = (1/pi) * arccos(sqrt(h^2 + 2*Re*h) / ((Re+h)*cos(beta)))

    Clamped to [0, 1].  At beta=0 (equinox SSO) eclipse is maximal.

    Args:
        altitude_km: Orbital altitude in km.
        beta_deg: Sun beta angle in degrees (0 = worst case).

    Returns:
        Fraction of orbit in eclipse [0..1].
    """
    re = _EARTH_RADIUS_M
    h = altitude_km * 1000.0
    beta_rad = math.radians(beta_deg)

    cos_beta = math.cos(beta_rad)
    if abs(cos_beta) < 1e-9:
        return 0.0  # full sun at beta=90

    numerator = math.sqrt(h ** 2 + 2.0 * re * h)
    denominator = (re + h) * cos_beta

    ratio = numerator / denominator
    if ratio >= 1.0:
        return 0.0  # no eclipse

    f_ecl = (1.0 / math.pi) * math.acos(ratio)
    return max(0.0, min(1.0, f_ecl))


def _solar_panel_power(design: CubeSatDesign) -> float:
    """Peak solar panel output power in watts.

    Reads the solar panel component from COMPONENT_CATALOG and adjusts
    for the selected solar configuration (body-mounted vs deployable).
    The catalog ``power_w`` is negative (generation); we return the
    absolute value scaled by the configuration multiplier.
    """
    solar_comp = COMPONENT_CATALOG["eps"]["components"][2]  # Solar Panel Array
    base_power = abs(solar_comp["power_w"])
    multiplier = _SOLAR_CONFIG_MULTIPLIER.get(design.solar_config, 1.0)
    return base_power * multiplier


def _battery_capacity_wh(design: CubeSatDesign) -> float:
    """Battery capacity in Wh from the catalog.

    Scales linearly with satellite size (larger sats carry more cells).
    """
    batt_comp = COMPONENT_CATALOG["eps"]["components"][1]  # Battery Pack
    base_capacity = batt_comp["properties"]["capacity_wh"]

    size_scale: dict[str, float] = {
        "1U": 1.0, "2U": 1.5, "3U": 2.0, "6U": 4.0, "12U": 8.0,
    }
    return base_capacity * size_scale.get(design.sat_size, 1.0)


# ---------------------------------------------------------------------------
# Public analyzer
# ---------------------------------------------------------------------------

class PowerProfileAnalyzer:
    """Orbital power profile analyzer for a CubeSat design.

    Simulates one full orbit at fine time resolution, tracking power
    generation, subsystem consumption (with duty cycles), and battery
    state of charge.  Checks energy balance and DoD constraints.

    Args:
        design: CubeSat design from the wizard.
        beta_deg: Sun beta angle (0 = worst-case equinox for SSO).
        duty_overrides: Optional dict to override default duty cycles.
    """

    def __init__(
        self,
        design: CubeSatDesign,
        beta_deg: float = 0.0,
        duty_overrides: dict[str, float] | None = None,
    ) -> None:
        self._design = design
        self._beta_deg = beta_deg
        self._duty_overrides = duty_overrides or {}
        self._result: PowerProfileResult | None = None

    # ------------------------------------------------------------------
    # Subsystem power bookkeeping
    # ------------------------------------------------------------------

    def _subsystem_powers(self) -> list[dict[str, Any]]:
        """Build a list of subsystem power entries with duty cycles.

        Returns:
            List of dicts with keys: name, power_w, duty_cycle.
        """
        entries: list[dict[str, Any]] = []

        for ss_id in self._design.subsystems:
            if ss_id not in COMPONENT_CATALOG:
                continue

            catalog = COMPONENT_CATALOG[ss_id]
            # Sum all positive-power components in this subsystem
            total_power = sum(
                c["power_w"]
                for c in catalog["components"]
                if c["power_w"] > 0
            )
            if total_power <= 0:
                continue

            duty = self._duty_overrides.get(
                ss_id, _DEFAULT_DUTY_CYCLES.get(ss_id, 1.0)
            )

            entries.append({
                "name": catalog["name"],
                "subsystem_id": ss_id,
                "power_w": total_power,
                "duty_cycle": duty,
            })

            # UHF has a continuous RX standby component
            if ss_id == "com_uhf":
                rx_power = total_power * _UHF_RX_POWER_FRACTION
                entries.append({
                    "name": "UHF RX Standby",
                    "subsystem_id": "com_uhf_rx",
                    "power_w": rx_power,
                    "duty_cycle": _UHF_RX_DUTY,
                })

        # Payload
        entries.append({
            "name": f"Payload ({self._design.payload_type})",
            "subsystem_id": "payload",
            "power_w": self._design.payload_power,
            "duty_cycle": self._duty_overrides.get("payload", 1.0),
        })

        return entries

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyze(self) -> PowerProfileResult:
        """Calculate full-orbit power profile.

        Steps:
        1. Compute orbit period from Kepler's third law.
        2. Determine eclipse fraction from orbit geometry.
        3. Step through one orbit, computing instantaneous generation
           and consumption.
        4. Track battery SoC to determine depth of discharge.
        5. Compute maximum payload duty cycle that satisfies energy balance.

        Returns:
            ``PowerProfileResult`` with all computed values.
        """
        # Orbital parameters
        period_s = _orbit_period_seconds(self._design.orbit_altitude)
        period_min = period_s / _SECONDS_PER_MINUTE
        ecl_frac = _eclipse_fraction(self._design.orbit_altitude, self._beta_deg)
        eclipse_min = period_min * ecl_frac
        sunlit_min = period_min * (1.0 - ecl_frac)

        # Power parameters
        peak_solar_w = _solar_panel_power(self._design)
        batt_cap_wh = _battery_capacity_wh(self._design)
        subsystems = self._subsystem_powers()

        # Peak consumption (all at 100% duty simultaneously)
        peak_consumption = sum(s["power_w"] for s in subsystems)

        # Orbit-average consumption (with duty cycles)
        avg_consumption = sum(
            s["power_w"] * s["duty_cycle"] for s in subsystems
        )

        # Orbit-average generation (sunlit fraction, EPS efficiency)
        avg_generation = peak_solar_w * (1.0 - ecl_frac) * _EPS_EFFICIENCY

        # Energy balance
        energy_balance = avg_generation >= avg_consumption

        # Battery DoD: energy consumed during eclipse / usable capacity
        eclipse_energy_wh = avg_consumption * (eclipse_min / 60.0)
        usable_capacity_wh = batt_cap_wh * _BATTERY_EFFICIENCY
        dod_percent = (
            (eclipse_energy_wh / usable_capacity_wh) * 100.0
            if usable_capacity_wh > 0
            else 100.0
        )

        # Battery cycles per year
        orbits_per_year = _SECONDS_PER_YEAR / period_s
        cycles_per_year = int(orbits_per_year)

        # Maximum payload duty cycle for energy balance
        # avg_gen >= sum(non-payload * duty) + payload_power * duty_payload
        non_payload_avg = sum(
            s["power_w"] * s["duty_cycle"]
            for s in subsystems
            if s["subsystem_id"] != "payload"
        )
        if self._design.payload_power > 0:
            max_payload_duty = max(
                0.0,
                min(1.0, (avg_generation - non_payload_avg) / self._design.payload_power),
            )
        else:
            max_payload_duty = 1.0

        # Margin
        margin_pct = (
            (avg_generation - avg_consumption) / avg_generation * 100.0
            if avg_generation > 0
            else -100.0
        )

        # Time-domain simulation for profile_data
        dt_min = _TIME_STEP_MINUTES
        dt_h = dt_min / 60.0
        steps = int(period_min / dt_min)
        sunlit_end_min = sunlit_min  # sunlit first, then eclipse

        profile_data: list[dict[str, float]] = []
        soc = 100.0  # start fully charged

        for step in range(steps):
            t_min = step * dt_min
            in_sunlight = t_min < sunlit_end_min

            # Generation
            if in_sunlight:
                # Simple cosine model for sun angle variation
                phase = math.pi * (t_min / sunlit_end_min)
                sun_factor = max(0.0, math.sin(phase))
                power_gen = peak_solar_w * sun_factor * _EPS_EFFICIENCY
            else:
                power_gen = 0.0

            # Consumption (duty-cycle average)
            power_cons = avg_consumption

            # Battery SoC update
            net_power = power_gen - power_cons
            delta_energy_wh = net_power * dt_h
            if usable_capacity_wh > 0:
                soc += (delta_energy_wh / usable_capacity_wh) * 100.0
                soc = max(0.0, min(100.0, soc))

            profile_data.append({
                "time_min": round(t_min, 1),
                "power_gen_w": round(power_gen, 3),
                "power_cons_w": round(power_cons, 3),
                "battery_soc_pct": round(soc, 2),
                "in_sunlight": 1.0 if in_sunlight else 0.0,
            })

        self._result = PowerProfileResult(
            orbit_period_min=round(period_min, 2),
            eclipse_duration_min=round(eclipse_min, 2),
            sunlit_duration_min=round(sunlit_min, 2),
            solar_power_w=round(peak_solar_w, 2),
            avg_generation_w=round(avg_generation, 3),
            avg_consumption_w=round(avg_consumption, 3),
            peak_consumption_w=round(peak_consumption, 3),
            battery_capacity_wh=round(batt_cap_wh, 2),
            battery_depth_of_discharge=round(dod_percent, 2),
            battery_cycles_per_year=cycles_per_year,
            energy_balance_positive=energy_balance,
            duty_cycle_payload=round(max_payload_duty, 4),
            margin_percent=round(margin_pct, 2),
            profile_data=profile_data,
        )
        return self._result

    # ------------------------------------------------------------------
    # Pipeline integration
    # ------------------------------------------------------------------

    def to_analysis_result(self) -> AnalysisResult:
        """Convert power profile to a standard ``AnalysisResult``.

        PASS when energy balance is positive and DoD is below 20%.
        WARN when DoD exceeds 20% but energy balance is positive.
        FAIL when energy balance is negative.
        """
        if self._result is None:
            self.analyze()
        result = self._result
        assert result is not None  # satisfy type checker

        violations: list[Violation] = []

        # Energy balance check
        if not result.energy_balance_positive:
            violations.append(
                Violation(
                    rule_id="POWER-PROFILE-001",
                    severity=Severity.ERROR,
                    message=(
                        f"Negative energy balance: generation "
                        f"{result.avg_generation_w:.2f} W < consumption "
                        f"{result.avg_consumption_w:.2f} W (orbit average)"
                    ),
                    component_path="spacecraft/power/profile",
                    details={
                        "avg_generation_w": result.avg_generation_w,
                        "avg_consumption_w": result.avg_consumption_w,
                        "margin_percent": result.margin_percent,
                    },
                )
            )

        # DoD check
        if result.battery_depth_of_discharge > _MAX_DOD_PERCENT:
            severity = (
                Severity.ERROR
                if result.battery_depth_of_discharge > 40.0
                else Severity.WARNING
            )
            violations.append(
                Violation(
                    rule_id="POWER-PROFILE-002",
                    severity=severity,
                    message=(
                        f"Battery DoD {result.battery_depth_of_discharge:.1f}% "
                        f"exceeds {_MAX_DOD_PERCENT:.0f}% limit for "
                        f"{self._design.design_life:.0f}-year life"
                    ),
                    component_path="spacecraft/power/battery",
                    details={
                        "dod_percent": result.battery_depth_of_discharge,
                        "limit_percent": _MAX_DOD_PERCENT,
                        "cycles_per_year": result.battery_cycles_per_year,
                        "design_life_years": self._design.design_life,
                    },
                )
            )

        # Margin check (< 10% is tight)
        if result.energy_balance_positive and result.margin_percent < 10.0:
            violations.append(
                Violation(
                    rule_id="POWER-PROFILE-003",
                    severity=Severity.WARNING,
                    message=(
                        f"Power margin {result.margin_percent:.1f}% is below "
                        f"10% recommended minimum"
                    ),
                    component_path="spacecraft/power/profile",
                    details={"margin_percent": result.margin_percent},
                )
            )

        has_error = any(v.severity == Severity.ERROR for v in violations)
        has_warning = any(v.severity == Severity.WARNING for v in violations)
        status = (
            AnalysisStatus.FAIL
            if has_error
            else AnalysisStatus.WARN
            if has_warning
            else AnalysisStatus.PASS
        )

        return AnalysisResult(
            analyzer="power_profile",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary={
                "orbit_period_min": result.orbit_period_min,
                "eclipse_min": result.eclipse_duration_min,
                "sunlit_min": result.sunlit_duration_min,
                "solar_peak_w": result.solar_power_w,
                "avg_generation_w": result.avg_generation_w,
                "avg_consumption_w": result.avg_consumption_w,
                "peak_consumption_w": result.peak_consumption_w,
                "battery_wh": result.battery_capacity_wh,
                "dod_percent": result.battery_depth_of_discharge,
                "cycles_per_year": result.battery_cycles_per_year,
                "energy_balance": result.energy_balance_positive,
                "max_payload_duty": result.duty_cycle_payload,
                "margin_percent": result.margin_percent,
            },
            metadata={
                "orbit_altitude_km": self._design.orbit_altitude,
                "beta_deg": self._beta_deg,
                "solar_config": self._design.solar_config,
                "battery_type": self._design.battery_type,
                "sat_size": self._design.sat_size,
            },
        )

    # ------------------------------------------------------------------
    # Report formatting
    # ------------------------------------------------------------------

    def format_report(self) -> str:
        """Generate an ASCII report with orbit timeline and power bars.

        Returns:
            Formatted multi-line string for terminal output.
        """
        if self._result is None:
            self.analyze()
        r = self._result
        assert r is not None

        w = 62
        lines: list[str] = []

        lines.append("=" * w)
        lines.append(
            f"  Power Profile -- {self._design.mission_name} "
            f"({self._design.sat_size})"
        )
        lines.append("=" * w)
        lines.append("")

        # Orbit parameters
        lines.append("  Orbit Parameters")
        lines.append("  " + "-" * (w - 4))
        lines.append(f"  Altitude:           {self._design.orbit_altitude:.0f} km")
        lines.append(f"  Period:             {r.orbit_period_min:.1f} min")
        lines.append(f"  Sunlit:             {r.sunlit_duration_min:.1f} min")
        lines.append(f"  Eclipse:            {r.eclipse_duration_min:.1f} min")
        lines.append(f"  Beta angle:         {self._beta_deg:.1f} deg")
        lines.append("")

        # Power budget
        lines.append("  Power Budget")
        lines.append("  " + "-" * (w - 4))
        lines.append(f"  Solar peak:         {r.solar_power_w:.1f} W  ({self._design.solar_config})")
        lines.append(f"  Avg generation:     {r.avg_generation_w:.2f} W")
        lines.append(f"  Avg consumption:    {r.avg_consumption_w:.2f} W")
        lines.append(f"  Peak consumption:   {r.peak_consumption_w:.2f} W")
        balance_str = "POSITIVE" if r.energy_balance_positive else "NEGATIVE"
        lines.append(f"  Energy balance:     {balance_str} ({r.margin_percent:+.1f}%)")
        lines.append(f"  Max payload duty:   {r.duty_cycle_payload:.1%}")
        lines.append("")

        # Battery
        lines.append("  Battery")
        lines.append("  " + "-" * (w - 4))
        lines.append(f"  Capacity:           {r.battery_capacity_wh:.1f} Wh  ({self._design.battery_type})")
        lines.append(f"  Depth of discharge: {r.battery_depth_of_discharge:.1f}%")
        dod_ok = "OK" if r.battery_depth_of_discharge <= _MAX_DOD_PERCENT else "EXCEEDS LIMIT"
        lines.append(f"  DoD limit (20%):    {dod_ok}")
        lines.append(f"  Cycles/year:        {r.battery_cycles_per_year}")
        lines.append("")

        # Orbit timeline bar
        lines.append("  Orbit Timeline")
        lines.append("  " + "-" * (w - 4))
        bar_width = 50
        sunlit_chars = int(bar_width * (r.sunlit_duration_min / r.orbit_period_min))
        eclipse_chars = bar_width - sunlit_chars
        bar = "#" * sunlit_chars + "." * eclipse_chars
        lines.append(f"  [{bar}]")
        lines.append(f"  {'#=sunlit':<{sunlit_chars + 3}}{'.=eclipse'}")
        lines.append("")

        # SoC profile (sampled at ~10 points)
        lines.append("  Battery SoC Profile")
        lines.append("  " + "-" * (w - 4))
        if r.profile_data:
            sample_interval = max(1, len(r.profile_data) // 12)
            lines.append(f"  {'Time(min)':>10}  {'Gen(W)':>8}  {'Con(W)':>8}  {'SoC(%)':>8}  Bar")
            for i in range(0, len(r.profile_data), sample_interval):
                p = r.profile_data[i]
                soc_bar_len = int(p["battery_soc_pct"] / 100.0 * 20)
                soc_bar = "|" * soc_bar_len
                sun_marker = "*" if p["in_sunlight"] > 0.5 else " "
                lines.append(
                    f"  {p['time_min']:>9.1f}{sun_marker} "
                    f"{p['power_gen_w']:>8.2f}  "
                    f"{p['power_cons_w']:>8.2f}  "
                    f"{p['battery_soc_pct']:>7.1f}%  "
                    f"{soc_bar}"
                )

        lines.append("")
        lines.append("=" * w)

        return "\n".join(lines)
