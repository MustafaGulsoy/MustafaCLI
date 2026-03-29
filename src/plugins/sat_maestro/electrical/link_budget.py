"""Communication link budget calculator for UHF and S-Band CubeSat links.

Implements free-space path loss (FSPL) link budget analysis following
ITU-R P.525 methodology.  Calculates Eb/N0, compares against required
thresholds for BPSK and QPSK modulation, and produces a standard
``AnalysisResult`` for integration with the auto-analysis pipeline.
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
from ..cubesat_wizard import COMPONENT_CATALOG, CubeSatDesign

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
_EARTH_RADIUS_KM: float = 6371.0
_BOLTZMANN_DBW_HZ_K: float = -228.6  # 10*log10(k) in dBW/(Hz*K)

# ---------------------------------------------------------------------------
# Ground station defaults (typical amateur / university station)
# ---------------------------------------------------------------------------
_GS_UHF_ANTENNA_GAIN_DBI: float = 14.0  # Yagi
_GS_SBAND_ANTENNA_GAIN_DBI: float = 20.0  # Parabolic dish
_GS_SYSTEM_NOISE_TEMP_K: float = 300.0  # ambient + LNA

# ---------------------------------------------------------------------------
# Modulation thresholds (Eb/N0 for BER = 1e-5)
# ---------------------------------------------------------------------------
_REQUIRED_EB_NO_BPSK: float = 9.6  # dB, BPSK coherent
_REQUIRED_EB_NO_QPSK: float = 9.6  # same Eb/N0 as BPSK (same BER curve)

# ---------------------------------------------------------------------------
# Default elevation for worst-case slant range
# ---------------------------------------------------------------------------
_MIN_ELEVATION_DEG: float = 5.0

# ---------------------------------------------------------------------------
# Implementation margin / atmospheric losses
# ---------------------------------------------------------------------------
_ATMOSPHERIC_LOSS_UHF_DB: float = 1.0
_ATMOSPHERIC_LOSS_SBAND_DB: float = 2.0
_IMPLEMENTATION_LOSS_DB: float = 2.0  # cable, connector, pointing


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class LinkBudgetResult:
    """Single link budget calculation result."""

    frequency_mhz: float
    tx_power_dbm: float
    tx_antenna_gain_dbi: float
    path_loss_db: float
    atmospheric_loss_db: float
    implementation_loss_db: float
    rx_antenna_gain_dbi: float
    system_noise_temp_k: float
    data_rate_bps: float
    eb_no_db: float
    required_eb_no_db: float
    link_margin_db: float
    slant_range_km: float
    status: str  # "PASS" or "FAIL"

    @property
    def is_pass(self) -> bool:
        """Return True when the link closes with positive margin."""
        return self.link_margin_db >= 0.0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _slant_range_km(altitude_km: float, elevation_deg: float) -> float:
    """Compute slant range from satellite altitude and ground elevation angle.

    Uses the geometric relation for a circular orbit:
        d = sqrt((Re+h)^2 - Re^2 * cos^2(el)) - Re * sin(el)

    Args:
        altitude_km: Orbital altitude above Earth surface in km.
        elevation_deg: Ground station elevation angle in degrees.

    Returns:
        Slant range in kilometres.
    """
    re = _EARTH_RADIUS_KM
    h = altitude_km
    el_rad = math.radians(elevation_deg)

    term_a = (re + h) ** 2
    term_b = (re * math.cos(el_rad)) ** 2
    slant = math.sqrt(term_a - term_b) - re * math.sin(el_rad)
    return max(slant, h)  # never less than straight overhead


def _fspl_db(distance_km: float, frequency_mhz: float) -> float:
    """Free-space path loss in dB (ITU-R P.525).

    FSPL = 20*log10(d_km) + 20*log10(f_MHz) + 32.45

    Args:
        distance_km: Propagation distance in km.
        frequency_mhz: Carrier frequency in MHz.

    Returns:
        Path loss in dB (positive value).
    """
    if distance_km <= 0 or frequency_mhz <= 0:
        return 0.0
    return (
        20.0 * math.log10(distance_km)
        + 20.0 * math.log10(frequency_mhz)
        + 32.45
    )


def _compute_link_budget(
    freq_mhz: float,
    tx_power_dbm: float,
    tx_gain_dbi: float,
    rx_gain_dbi: float,
    slant_range_km: float,
    system_noise_temp_k: float,
    data_rate_bps: float,
    required_eb_no_db: float,
    atmospheric_loss_db: float,
    implementation_loss_db: float,
) -> LinkBudgetResult:
    """Core link budget computation.

    Signal chain (all dB):
        EIRP = Ptx + Gtx
        Received C = EIRP - FSPL - atm_loss - impl_loss + Grx
        C/N0 = C - 10*log10(k*Tsys) = C + 228.6 - 10*log10(Tsys)
        Eb/N0 = C/N0 - 10*log10(Rb)
        Margin = Eb/N0 - required_Eb/N0
    """
    fspl = _fspl_db(slant_range_km, freq_mhz)

    # EIRP (dBm)
    eirp_dbm = tx_power_dbm + tx_gain_dbi

    # Received power (dBm)
    received_dbm = (
        eirp_dbm
        - fspl
        - atmospheric_loss_db
        - implementation_loss_db
        + rx_gain_dbi
    )

    # Convert to dBW for noise calculation
    received_dbw = received_dbm - 30.0

    # C/N0 (dB-Hz)
    # C/N0 = C(dBW) - k(dBW/Hz/K) - 10*log10(Tsys)
    c_n0 = received_dbw - _BOLTZMANN_DBW_HZ_K - 10.0 * math.log10(system_noise_temp_k)

    # Eb/N0 (dB)
    eb_no = c_n0 - 10.0 * math.log10(data_rate_bps)

    # Link margin
    margin = eb_no - required_eb_no_db

    status = "PASS" if margin >= 0.0 else "FAIL"

    return LinkBudgetResult(
        frequency_mhz=freq_mhz,
        tx_power_dbm=tx_power_dbm,
        tx_antenna_gain_dbi=tx_gain_dbi,
        path_loss_db=fspl,
        atmospheric_loss_db=atmospheric_loss_db,
        implementation_loss_db=implementation_loss_db,
        rx_antenna_gain_dbi=rx_gain_dbi,
        system_noise_temp_k=system_noise_temp_k,
        data_rate_bps=data_rate_bps,
        eb_no_db=round(eb_no, 2),
        required_eb_no_db=required_eb_no_db,
        link_margin_db=round(margin, 2),
        slant_range_km=round(slant_range_km, 1),
        status=status,
    )


# ---------------------------------------------------------------------------
# Public analyzer
# ---------------------------------------------------------------------------

class LinkBudgetAnalyzer:
    """Communication link budget analyzer for a CubeSat design.

    Evaluates UHF and S-Band links (when the corresponding subsystem is
    present in the design) against worst-case slant range at a configurable
    minimum elevation angle.

    Args:
        design: CubeSat design from the wizard.
        min_elevation_deg: Minimum ground-station elevation for worst case.
        gs_noise_temp_k: Ground-station system noise temperature.
    """

    def __init__(
        self,
        design: CubeSatDesign,
        min_elevation_deg: float = _MIN_ELEVATION_DEG,
        gs_noise_temp_k: float = _GS_SYSTEM_NOISE_TEMP_K,
    ) -> None:
        self._design = design
        self._min_elevation = min_elevation_deg
        self._gs_noise_temp = gs_noise_temp_k
        self._uhf_result: LinkBudgetResult | None = None
        self._sband_result: LinkBudgetResult | None = None

    # ------------------------------------------------------------------
    # Catalog parameter extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _uhf_params() -> dict[str, Any]:
        """Extract UHF link parameters from COMPONENT_CATALOG."""
        trx = COMPONENT_CATALOG["com_uhf"]["components"][0]  # transceiver
        ant = COMPONENT_CATALOG["com_uhf"]["components"][1]  # antenna
        return {
            "freq_mhz": trx["properties"]["freq_mhz"],
            "tx_power_dbm": trx["properties"]["tx_power_dbm"],
            "tx_gain_dbi": ant["properties"]["gain_dbi"],
            "data_rate_bps": trx["properties"]["data_rate_kbps"] * 1000.0,
        }

    @staticmethod
    def _sband_params() -> dict[str, Any]:
        """Extract S-Band link parameters from COMPONENT_CATALOG."""
        tx = COMPONENT_CATALOG["com_sband"]["components"][0]  # transmitter
        ant = COMPONENT_CATALOG["com_sband"]["components"][1]  # antenna
        return {
            "freq_mhz": tx["properties"]["freq_ghz"] * 1000.0,
            "tx_power_dbm": tx["properties"]["tx_power_dbm"],
            "tx_gain_dbi": ant["properties"]["gain_dbi"],
            "data_rate_bps": tx["properties"]["data_rate_mbps"] * 1e6,
        }

    # ------------------------------------------------------------------
    # Per-band analysis
    # ------------------------------------------------------------------

    def analyze_uhf(self) -> LinkBudgetResult:
        """UHF downlink budget at worst-case elevation.

        Parameters are sourced from ``COMPONENT_CATALOG["com_uhf"]``:
        - Frequency: 437 MHz
        - TX power: 30 dBm (1 W)
        - Satellite antenna gain: 2.1 dBi (deployable monopole)
        - Ground station: 14 dBi Yagi (typical amateur)
        - Data rate: 9.6 kbps, BPSK modulation

        The worst-case slant range is computed at the configured minimum
        elevation angle (default 5 degrees).
        """
        params = self._uhf_params()
        slant = _slant_range_km(self._design.orbit_altitude, self._min_elevation)

        self._uhf_result = _compute_link_budget(
            freq_mhz=params["freq_mhz"],
            tx_power_dbm=params["tx_power_dbm"],
            tx_gain_dbi=params["tx_gain_dbi"],
            rx_gain_dbi=_GS_UHF_ANTENNA_GAIN_DBI,
            slant_range_km=slant,
            system_noise_temp_k=self._gs_noise_temp,
            data_rate_bps=params["data_rate_bps"],
            required_eb_no_db=_REQUIRED_EB_NO_BPSK,
            atmospheric_loss_db=_ATMOSPHERIC_LOSS_UHF_DB,
            implementation_loss_db=_IMPLEMENTATION_LOSS_DB,
        )
        return self._uhf_result

    def analyze_sband(self) -> LinkBudgetResult:
        """S-Band downlink budget at worst-case elevation.

        Parameters are sourced from ``COMPONENT_CATALOG["com_sband"]``:
        - Frequency: 2.4 GHz (2400 MHz)
        - TX power: 27 dBm (0.5 W)
        - Satellite antenna gain: 7 dBi (patch antenna)
        - Ground station: 20 dBi dish
        - Data rate: 2 Mbps, QPSK modulation

        Higher atmospheric and pointing losses are applied compared
        to UHF due to the shorter wavelength.
        """
        params = self._sband_params()
        slant = _slant_range_km(self._design.orbit_altitude, self._min_elevation)

        self._sband_result = _compute_link_budget(
            freq_mhz=params["freq_mhz"],
            tx_power_dbm=params["tx_power_dbm"],
            tx_gain_dbi=params["tx_gain_dbi"],
            rx_gain_dbi=_GS_SBAND_ANTENNA_GAIN_DBI,
            slant_range_km=slant,
            system_noise_temp_k=self._gs_noise_temp,
            data_rate_bps=params["data_rate_bps"],
            required_eb_no_db=_REQUIRED_EB_NO_QPSK,
            atmospheric_loss_db=_ATMOSPHERIC_LOSS_SBAND_DB,
            implementation_loss_db=_IMPLEMENTATION_LOSS_DB,
        )
        return self._sband_result

    # ------------------------------------------------------------------
    # Pipeline integration
    # ------------------------------------------------------------------

    def analyze_all(self) -> list[LinkBudgetResult]:
        """Run link budgets for all communication subsystems in the design.

        Returns:
            List of ``LinkBudgetResult`` for each active comm band.
        """
        results: list[LinkBudgetResult] = []

        if "com_uhf" in self._design.subsystems:
            results.append(self.analyze_uhf())
        if "com_sband" in self._design.subsystems:
            results.append(self.analyze_sband())

        return results

    def to_analysis_result(self) -> AnalysisResult:
        """Convert link budget results to a standard ``AnalysisResult``.

        Runs analysis for all active bands if not already computed.
        Generates violations for any link that does not close (negative
        margin) and warnings for margins below 3 dB.
        """
        all_results = self.analyze_all()
        violations: list[Violation] = []
        summary: dict[str, Any] = {"bands_analyzed": len(all_results)}

        for result in all_results:
            band = "UHF" if result.frequency_mhz < 1000 else "S-Band"
            summary[f"{band.lower()}_margin_db"] = result.link_margin_db
            summary[f"{band.lower()}_eb_no_db"] = result.eb_no_db

            if result.link_margin_db < 0.0:
                violations.append(
                    Violation(
                        rule_id=f"LINK-BUDGET-{band.upper()}-001",
                        severity=Severity.ERROR,
                        message=(
                            f"{band} link does not close: margin "
                            f"{result.link_margin_db:+.1f} dB at "
                            f"{self._min_elevation:.0f} deg elevation "
                            f"(slant range {result.slant_range_km:.0f} km)"
                        ),
                        component_path=f"spacecraft/comms/{band.lower()}",
                        details={
                            "margin_db": result.link_margin_db,
                            "eb_no_db": result.eb_no_db,
                            "required_eb_no_db": result.required_eb_no_db,
                            "slant_range_km": result.slant_range_km,
                            "frequency_mhz": result.frequency_mhz,
                        },
                    )
                )
            elif result.link_margin_db < 3.0:
                violations.append(
                    Violation(
                        rule_id=f"LINK-BUDGET-{band.upper()}-002",
                        severity=Severity.WARNING,
                        message=(
                            f"{band} link margin {result.link_margin_db:+.1f} dB "
                            f"is below 3 dB recommended minimum"
                        ),
                        component_path=f"spacecraft/comms/{band.lower()}",
                        details={
                            "margin_db": result.link_margin_db,
                            "recommended_min_db": 3.0,
                        },
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
            analyzer="link_budget",
            status=status,
            timestamp=datetime.now(),
            violations=violations,
            summary=summary,
            metadata={
                "min_elevation_deg": self._min_elevation,
                "gs_noise_temp_k": self._gs_noise_temp,
                "orbit_altitude_km": self._design.orbit_altitude,
            },
        )

    # ------------------------------------------------------------------
    # Report formatting
    # ------------------------------------------------------------------

    def format_report(self) -> str:
        """Generate an ASCII table with link budget details.

        Runs analysis for all active bands if not already computed.

        Returns:
            Formatted multi-line string for terminal output.
        """
        all_results = self.analyze_all()

        if not all_results:
            return "No communication subsystems selected -- nothing to analyze."

        col_w = 22
        lines: list[str] = []

        header = f"{'Parameter':<32}"
        for r in all_results:
            band = "UHF" if r.frequency_mhz < 1000 else "S-Band"
            header += f" {band:>{col_w}}"
        sep = "-" * len(header)

        lines.append("=" * len(header))
        lines.append(
            f"  Communication Link Budget -- {self._design.mission_name}"
        )
        lines.append(
            f"  Orbit: {self._design.orbit_type} "
            f"{self._design.orbit_altitude:.0f} km, "
            f"min elevation {self._min_elevation:.0f} deg"
        )
        lines.append("=" * len(header))
        lines.append("")
        lines.append(header)
        lines.append(sep)

        rows: list[tuple[str, str]] = [
            ("Frequency", "frequency_mhz", "MHz", "{:.0f}"),
            ("TX Power", "tx_power_dbm", "dBm", "{:.1f}"),
            ("TX Antenna Gain", "tx_antenna_gain_dbi", "dBi", "{:.1f}"),
            ("Slant Range", "slant_range_km", "km", "{:.1f}"),
            ("Free-Space Path Loss", "path_loss_db", "dB", "{:.1f}"),
            ("Atmospheric Loss", "atmospheric_loss_db", "dB", "{:.1f}"),
            ("Implementation Loss", "implementation_loss_db", "dB", "{:.1f}"),
            ("RX Antenna Gain (GS)", "rx_antenna_gain_dbi", "dBi", "{:.1f}"),
            ("System Noise Temp", "system_noise_temp_k", "K", "{:.0f}"),
            ("Data Rate", "data_rate_bps", "bps", "{:.0f}"),
            ("Eb/N0", "eb_no_db", "dB", "{:.2f}"),
            ("Required Eb/N0", "required_eb_no_db", "dB", "{:.1f}"),
            ("Link Margin", "link_margin_db", "dB", "{:+.2f}"),
            ("Status", "status", "", "{}"),
        ]

        for label, attr, unit, fmt in rows:
            row_str = f"  {label:<30}"
            for r in all_results:
                val = getattr(r, attr)
                formatted = fmt.format(val)
                if unit:
                    formatted = f"{formatted} {unit}"
                row_str += f" {formatted:>{col_w}}"
            lines.append(row_str)

        lines.append(sep)
        lines.append("")

        return "\n".join(lines)
