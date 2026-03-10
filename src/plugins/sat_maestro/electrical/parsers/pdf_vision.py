"""PDF schematic analysis via LLM vision."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...config import SatMaestroConfig
from ...core.graph_models import Component, ComponentType, Net, NetType, Pin, PinDirection

logger = logging.getLogger(__name__)


@dataclass
class PdfVisionResult:
    """Result of PDF vision analysis."""
    components: list[Component] = field(default_factory=list)
    pins: list[Pin] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    raw_llm_response: str = ""
    source_file: str = ""


class PdfVisionParser:
    """Analyze PDF schematics using LLM vision capabilities."""

    EXTRACTION_PROMPT = """Analyze this circuit schematic image and extract all components, pins, and connections.

Return a JSON object with this exact structure:
{
    "components": [
        {"ref": "U1", "name": "STM32F4", "type": "IC", "pins": [
            {"name": "VCC", "direction": "power_in", "voltage": 3.3},
            {"name": "PA0", "direction": "bidirectional"}
        ]}
    ],
    "nets": [
        {"name": "NET_VCC", "type": "power", "pins": ["U1.VCC", "C1.1"]}
    ],
    "confidence": 0.85
}

Component types: IC, CONNECTOR, PASSIVE, MODULE
Pin directions: input, output, bidirectional, power_in, power_out
Net types: power, signal, ground

Be thorough and precise. Include ALL visible components and connections."""

    _TYPE_MAP = {
        "IC": ComponentType.IC,
        "CONNECTOR": ComponentType.CONNECTOR,
        "PASSIVE": ComponentType.PASSIVE,
        "MODULE": ComponentType.MODULE,
    }

    _DIR_MAP = {
        "input": PinDirection.INPUT,
        "output": PinDirection.OUTPUT,
        "bidirectional": PinDirection.BIDIRECTIONAL,
        "power_in": PinDirection.POWER,
        "power_out": PinDirection.POWER,
    }

    _NET_TYPE_MAP = {
        "power": NetType.POWER,
        "signal": NetType.SIGNAL,
        "ground": NetType.GROUND,
    }

    def __init__(self, config: SatMaestroConfig) -> None:
        self._config = config

    async def parse(self, pdf_path: str, subsystem: str = "default") -> PdfVisionResult:
        """Analyze a PDF schematic using LLM vision."""
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        if not self._config.llm_vision_enabled:
            return PdfVisionResult(
                source_file=str(path),
                warnings=["LLM vision is disabled in configuration"],
            )

        result = PdfVisionResult(source_file=str(path))

        # Read PDF pages as images
        pages = self._extract_pages(path)
        if not pages:
            result.warnings.append("Could not extract pages from PDF")
            return result

        # Analyze each page
        all_components: list[dict[str, Any]] = []
        all_nets: list[dict[str, Any]] = []
        total_confidence = 0.0

        for i, page_data in enumerate(pages):
            try:
                page_result = await self._analyze_page(page_data, subsystem, i + 1)
                all_components.extend(page_result.get("components", []))
                all_nets.extend(page_result.get("nets", []))
                total_confidence += page_result.get("confidence", 0.0)
            except Exception as e:
                result.warnings.append(f"Page {i + 1} analysis failed: {e}")

        if pages:
            result.confidence = total_confidence / len(pages)

        # Convert raw LLM data to our models
        self._convert_components(all_components, subsystem, result)
        self._convert_nets(all_nets, result)

        if result.confidence < 0.5:
            result.warnings.append(
                f"Low confidence ({result.confidence:.0%}). Manual verification recommended."
            )

        logger.info(
            "PDF vision analysis: %d components, %d nets, confidence: %.0f%%",
            len(result.components), len(result.nets), result.confidence * 100,
        )
        return result

    def _extract_pages(self, path: Path) -> list[bytes]:
        """Extract PDF pages as PNG images."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF not installed. PDF parsing unavailable.")
            return []

        pages: list[bytes] = []
        try:
            doc = fitz.open(str(path))
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                pages.append(pix.tobytes("png"))
            doc.close()
        except Exception as e:
            logger.error("Failed to extract PDF pages: %s", e)

        return pages

    async def _analyze_page(self, image_data: bytes, subsystem: str, page_num: int) -> dict[str, Any]:
        """Send a page image to LLM vision for analysis."""
        # This would integrate with the actual LLM provider
        # For now, return empty result - will be connected to Ollama vision
        logger.info("Analyzing page %d via LLM vision", page_num)
        return {"components": [], "nets": [], "confidence": 0.0}

    def _convert_components(self, raw_components: list[dict[str, Any]], subsystem: str, result: PdfVisionResult) -> None:
        """Convert raw LLM component data to graph models."""
        for comp_data in raw_components:
            ref = comp_data.get("ref", "UNKNOWN")
            comp_id = f"{subsystem}_{ref}"
            comp_type = self._TYPE_MAP.get(
                comp_data.get("type", "IC"), ComponentType.IC
            )

            component = Component(
                id=comp_id,
                name=f"{ref} ({comp_data.get('name', '')})",
                type=comp_type,
                subsystem=subsystem,
                properties={"source": "pdf_vision"},
            )
            result.components.append(component)

            for pin_data in comp_data.get("pins", []):
                pin_name = pin_data.get("name", "")
                pin_dir = self._DIR_MAP.get(
                    pin_data.get("direction", "bidirectional"),
                    PinDirection.BIDIRECTIONAL,
                )
                pin = Pin(
                    id=f"{comp_id}_{pin_name}",
                    name=pin_name,
                    direction=pin_dir,
                    component_id=comp_id,
                    voltage=pin_data.get("voltage"),
                    current_max=pin_data.get("current_max"),
                )
                result.pins.append(pin)

    def _convert_nets(self, raw_nets: list[dict[str, Any]], result: PdfVisionResult) -> None:
        """Convert raw LLM net data to graph models."""
        for i, net_data in enumerate(raw_nets):
            net_name = net_data.get("name", f"net_{i}")
            net_type = self._NET_TYPE_MAP.get(
                net_data.get("type", "signal"), NetType.SIGNAL
            )
            pin_ids = net_data.get("pins", [])

            result.nets.append(Net(
                id=f"pdf_net_{i}",
                name=net_name,
                type=net_type,
                pin_ids=pin_ids,
            ))

    @staticmethod
    def parse_llm_json(response: str) -> dict[str, Any]:
        """Safely extract JSON from LLM response text."""
        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in markdown
        json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find any {...} block
        brace_match = re.search(r"\{.*\}", response, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return {}
