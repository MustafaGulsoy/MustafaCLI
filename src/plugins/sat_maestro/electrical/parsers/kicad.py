"""KiCad schematic and PCB parser."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...core.graph_models import Component, ComponentType, Net, NetType, Pin, PinDirection

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Result of parsing an engineering file."""
    components: list[Component] = field(default_factory=list)
    pins: list[Pin] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_file: str = ""


class KiCadParser:
    """Parse KiCad schematic (.kicad_sch) and PCB (.kicad_pcb) files."""

    # Map KiCad component types to our types
    _TYPE_MAP = {
        "R": ComponentType.PASSIVE,
        "C": ComponentType.PASSIVE,
        "L": ComponentType.PASSIVE,
        "U": ComponentType.IC,
        "J": ComponentType.CONNECTOR,
        "P": ComponentType.CONNECTOR,
        "Q": ComponentType.IC,
        "D": ComponentType.PASSIVE,
    }

    _PIN_DIR_MAP = {
        "input": PinDirection.INPUT,
        "output": PinDirection.OUTPUT,
        "bidirectional": PinDirection.BIDIRECTIONAL,
        "power_in": PinDirection.POWER,
        "power_out": PinDirection.POWER,
        "passive": PinDirection.BIDIRECTIONAL,
        "tri_state": PinDirection.OUTPUT,
        "unspecified": PinDirection.BIDIRECTIONAL,
    }

    def parse(self, file_path: str, subsystem: str = "default") -> ParseResult:
        """Parse a KiCad file and extract components, pins, and nets."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"KiCad file not found: {file_path}")

        suffix = path.suffix.lower()
        if suffix == ".kicad_sch":
            return self._parse_schematic(path, subsystem)
        elif suffix == ".kicad_pcb":
            return self._parse_pcb(path, subsystem)
        else:
            raise ValueError(f"Unsupported KiCad file type: {suffix}")

    def _parse_schematic(self, path: Path, subsystem: str) -> ParseResult:
        """Parse a KiCad schematic file (S-expression format)."""
        result = ParseResult(source_file=str(path))

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")

        # Parse symbols (components)
        self._extract_symbols(content, subsystem, result)
        # Parse wires/nets
        self._extract_nets(content, result)

        logger.info(
            "Parsed KiCad schematic: %d components, %d pins, %d nets",
            len(result.components), len(result.pins), len(result.nets),
        )
        return result

    def _parse_pcb(self, path: Path, subsystem: str) -> ParseResult:
        """Parse a KiCad PCB file."""
        result = ParseResult(source_file=str(path))

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")

        # Extract footprints as components
        self._extract_footprints(content, subsystem, result)
        # Extract net definitions
        self._extract_pcb_nets(content, result)

        logger.info(
            "Parsed KiCad PCB: %d components, %d nets",
            len(result.components), len(result.nets),
        )
        return result

    def _extract_symbols(self, content: str, subsystem: str, result: ParseResult) -> None:
        """Extract component symbols from schematic content."""
        # Match (symbol (lib_id "ref:name") ... (property "Reference" "U1") ...)
        symbol_pattern = r'\(symbol\s+\(lib_id\s+"([^"]+)"\)(.*?)\n\s*\)'
        ref_pattern = r'\(property\s+"Reference"\s+"([^"]+)"'
        value_pattern = r'\(property\s+"Value"\s+"([^"]+)"'
        pin_pattern = (
            r'\(pin\s+(\w+)\s+\w+\s+'
            r'\(at\s+[\d.\-\s]+\)\s+'
            r'\(length\s+[\d.]+\)'
            r'(?:\s+\(name\s+"([^"]+)"\))?'
        )

        for match in re.finditer(symbol_pattern, content, re.DOTALL):
            lib_id = match.group(1)
            body = match.group(2)

            ref_match = re.search(ref_pattern, body)
            value_match = re.search(value_pattern, body)

            if not ref_match:
                continue

            ref = ref_match.group(1)
            value = value_match.group(1) if value_match else lib_id

            # Determine component type from reference prefix
            prefix = re.match(r"([A-Z]+)", ref)
            comp_type = self._TYPE_MAP.get(
                prefix.group(1) if prefix else "", ComponentType.IC
            )

            comp_id = f"{subsystem}_{ref}"
            component = Component(
                id=comp_id,
                name=f"{ref} ({value})",
                type=comp_type,
                subsystem=subsystem,
                properties={"lib_id": lib_id, "value": value, "reference": ref},
            )
            result.components.append(component)

            # Extract pins for this symbol
            for pin_match in re.finditer(pin_pattern, body, re.DOTALL):
                pin_type = pin_match.group(1)
                pin_name = pin_match.group(2) or pin_type
                pin_dir = self._PIN_DIR_MAP.get(pin_type, PinDirection.BIDIRECTIONAL)

                pin = Pin(
                    id=f"{comp_id}_{pin_name}",
                    name=pin_name,
                    direction=pin_dir,
                    component_id=comp_id,
                )
                result.pins.append(pin)

    def _extract_nets(self, content: str, result: ParseResult) -> None:
        """Extract nets from schematic wire connections."""
        # Match (net (code N) (name "NET_NAME"))
        net_pattern = r'\(net\s+\(code\s+(\d+)\)\s+\(name\s+"([^"]+)"\)\)'
        for match in re.finditer(net_pattern, content):
            net_id = f"net_{match.group(1)}"
            net_name = match.group(2)

            net_type = NetType.SIGNAL
            name_upper = net_name.upper()
            if any(kw in name_upper for kw in ["VCC", "VDD", "3V3", "5V", "12V", "PWR"]):
                net_type = NetType.POWER
            elif any(kw in name_upper for kw in ["GND", "VSS", "GROUND", "AGND", "DGND"]):
                net_type = NetType.GROUND

            result.nets.append(Net(id=net_id, name=net_name, type=net_type))

    def _extract_footprints(self, content: str, subsystem: str, result: ParseResult) -> None:
        """Extract footprints from PCB content."""
        fp_pattern = r'\(footprint\s+"([^"]+)"(.*?)\n\s*\)'
        ref_pattern = r'\(fp_text\s+reference\s+"([^"]+)"'

        for match in re.finditer(fp_pattern, content, re.DOTALL):
            lib = match.group(1)
            body = match.group(2)

            ref_match = re.search(ref_pattern, body)
            ref = ref_match.group(1) if ref_match else lib

            prefix = re.match(r"([A-Z]+)", ref)
            comp_type = self._TYPE_MAP.get(
                prefix.group(1) if prefix else "", ComponentType.IC
            )

            comp_id = f"{subsystem}_{ref}"
            result.components.append(Component(
                id=comp_id,
                name=ref,
                type=comp_type,
                subsystem=subsystem,
                properties={"footprint": lib},
            ))

    def _extract_pcb_nets(self, content: str, result: ParseResult) -> None:
        """Extract net definitions from PCB file."""
        net_pattern = r'\(net\s+(\d+)\s+"([^"]+)"\)'
        for match in re.finditer(net_pattern, content):
            net_id = f"pcb_net_{match.group(1)}"
            net_name = match.group(2)

            net_type = NetType.SIGNAL
            name_upper = net_name.upper()
            if any(kw in name_upper for kw in ["VCC", "VDD", "3V3", "5V"]):
                net_type = NetType.POWER
            elif any(kw in name_upper for kw in ["GND", "VSS"]):
                net_type = NetType.GROUND

            result.nets.append(Net(id=net_id, name=net_name, type=net_type))
