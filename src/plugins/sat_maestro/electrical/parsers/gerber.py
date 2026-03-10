"""Gerber RS-274X file parser."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GerberPad:
    """Represents a pad extracted from Gerber data."""
    id: str
    x: float
    y: float
    aperture: str
    layer: str = ""
    net_name: str = ""


@dataclass
class GerberTrace:
    """Represents a trace/track from Gerber data."""
    id: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    width: float
    layer: str = ""
    net_name: str = ""


@dataclass
class GerberResult:
    """Result of parsing Gerber files."""
    pads: list[GerberPad] = field(default_factory=list)
    traces: list[GerberTrace] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    apertures: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    source_file: str = ""


class GerberParser:
    """Parse Gerber RS-274X files for PCB manufacturing data."""

    def parse(self, file_path: str) -> GerberResult:
        """Parse a Gerber file and extract pads and traces."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Gerber file not found: {file_path}")

        content = path.read_text(encoding="utf-8", errors="replace")
        result = GerberResult(source_file=str(path))

        self._parse_apertures(content, result)
        self._parse_draws(content, result)

        logger.info(
            "Parsed Gerber: %d pads, %d traces, %d apertures",
            len(result.pads), len(result.traces), len(result.apertures),
        )
        return result

    def parse_directory(self, dir_path: str) -> list[GerberResult]:
        """Parse all Gerber files in a directory."""
        path = Path(dir_path)
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        results = []
        gerber_extensions = {".gbr", ".ger", ".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".gtp", ".gbp"}

        for file in sorted(path.iterdir()):
            if file.suffix.lower() in gerber_extensions:
                try:
                    result = self.parse(str(file))
                    layer = self._detect_layer(file.suffix.lower())
                    result.layers.append(layer)
                    results.append(result)
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", file, e)

        return results

    def _parse_apertures(self, content: str, result: GerberResult) -> None:
        """Parse aperture definitions (%AD...)."""
        # Format: %ADD<code><type>,<params>*%
        ap_pattern = r"%ADD(\d+)([A-Z]+),?([\d.X]*)[\*]?%"
        for match in re.finditer(ap_pattern, content):
            code = f"D{match.group(1)}"
            shape = match.group(2)
            params = match.group(3)
            result.apertures[code] = {"shape": shape, "params": params}

    def _parse_draws(self, content: str, result: GerberResult) -> None:
        """Parse draw commands (D01=draw, D02=move, D03=flash/pad)."""
        current_aperture = ""
        current_x = 0.0
        current_y = 0.0
        pad_count = 0
        trace_count = 0

        # Coordinate format (usually 2.4 or 2.5)
        coord_scale = 1e-4  # default 2.4 format

        fs_match = re.search(r"%FSLAX(\d)(\d)Y\d+\*%", content)
        if fs_match:
            decimal_places = int(fs_match.group(2))
            coord_scale = 10 ** (-decimal_places)

        for line in content.splitlines():
            line = line.strip()

            # Aperture selection: D<code>*
            ap_match = re.match(r"^(D\d+)\*$", line)
            if ap_match and int(ap_match.group(1)[1:]) >= 10:
                current_aperture = ap_match.group(1)
                continue

            # Coordinate commands
            coord_match = re.match(
                r"^X(-?\d+)?Y(-?\d+)?D(\d+)\*$", line
            )
            if not coord_match:
                continue

            x_str = coord_match.group(1)
            y_str = coord_match.group(2)
            d_code = int(coord_match.group(3))

            new_x = float(x_str) * coord_scale if x_str else current_x
            new_y = float(y_str) * coord_scale if y_str else current_y

            if d_code == 3:  # Flash = pad
                pad_count += 1
                result.pads.append(GerberPad(
                    id=f"pad_{pad_count}",
                    x=new_x,
                    y=new_y,
                    aperture=current_aperture,
                ))
            elif d_code == 1:  # Draw = trace
                trace_count += 1
                width = 0.0
                ap_info = result.apertures.get(current_aperture, {})
                if ap_info.get("shape") == "C" and ap_info.get("params"):
                    try:
                        width = float(ap_info["params"])
                    except ValueError:
                        pass

                result.traces.append(GerberTrace(
                    id=f"trace_{trace_count}",
                    start_x=current_x,
                    start_y=current_y,
                    end_x=new_x,
                    end_y=new_y,
                    width=width,
                ))

            current_x = new_x
            current_y = new_y

    def _detect_layer(self, suffix: str) -> str:
        """Detect PCB layer from file extension."""
        layer_map = {
            ".gtl": "Top Copper",
            ".gbl": "Bottom Copper",
            ".gts": "Top Soldermask",
            ".gbs": "Bottom Soldermask",
            ".gto": "Top Silkscreen",
            ".gbo": "Bottom Silkscreen",
            ".gtp": "Top Paste",
            ".gbp": "Bottom Paste",
        }
        return layer_map.get(suffix, "Unknown")
