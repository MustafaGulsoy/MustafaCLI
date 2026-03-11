"""CalculiX result file parser (.dat/.frd)."""
from __future__ import annotations

import logging
import math
import re
from typing import Any

logger = logging.getLogger(__name__)


class CalculixResultParser:
    """Parse CalculiX output files (.dat and .frd)."""

    def parse_dat_frequencies(self, content: str) -> list[dict[str, Any]]:
        """Extract modal frequencies from .dat eigenvalue output."""
        frequencies = []
        pattern = r'(\d+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)'

        in_eigen_section = False
        for line in content.split("\n"):
            if "E I G E N V A L U E" in line or ("EIGENVALUE" in line and "OUTPUT" in line):
                in_eigen_section = True
                continue
            if in_eigen_section:
                match = re.match(pattern, line.strip())
                if match:
                    mode = int(match.group(1))
                    eigenvalue = float(match.group(2))
                    freq_hz = float(match.group(4))
                    frequencies.append({
                        "mode": mode,
                        "eigenvalue": eigenvalue,
                        "frequency_hz": freq_hz,
                    })

        return frequencies

    def parse_dat_stress(self, content: str) -> dict[str, Any]:
        """Extract stress values from .dat stress output."""
        elements = []
        max_von_mises = 0.0

        pattern = r'(\d+)\s+(\d+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)'

        for line in content.split("\n"):
            match = re.match(pattern, line.strip())
            if match:
                sxx = float(match.group(3))
                syy = float(match.group(4))
                szz = float(match.group(5))
                sxy = float(match.group(6))
                sxz = float(match.group(7))
                syz = float(match.group(8))

                von_mises = math.sqrt(0.5 * (
                    (sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2
                    + 6 * (sxy**2 + sxz**2 + syz**2)
                ))

                max_von_mises = max(max_von_mises, von_mises)
                elements.append({
                    "element": int(match.group(1)),
                    "node": int(match.group(2)),
                    "von_mises": von_mises,
                })

        return {"max_von_mises": max_von_mises, "elements": elements}

    def parse_dat_displacement(self, content: str) -> dict[str, Any]:
        """Extract displacement values from .dat output."""
        max_disp = 0.0
        nodes = []

        pattern = r'(\d+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)'

        in_disp_section = False
        for line in content.split("\n"):
            if "DISPLACEMENTS" in line:
                in_disp_section = True
                continue
            if in_disp_section:
                match = re.match(pattern, line.strip())
                if match:
                    dx = float(match.group(2))
                    dy = float(match.group(3))
                    dz = float(match.group(4))
                    mag = math.sqrt(dx**2 + dy**2 + dz**2)
                    max_disp = max(max_disp, mag)
                    nodes.append({
                        "node": int(match.group(1)),
                        "displacement": mag,
                    })

        return {"max_displacement": max_disp, "nodes": nodes}
