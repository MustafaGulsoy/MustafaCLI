"""API mapper - REST endpoint detection for various frameworks."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import ArchAnalyzerConfig


@dataclass
class ApiEndpoint:
    """A detected API endpoint."""

    method: str
    path: str
    handler: str
    source_file: str
    line_number: int = 0
    framework: str = ""


@dataclass
class ApiMap:
    """Collection of all detected API endpoints."""

    endpoints: list[ApiEndpoint] = field(default_factory=list)
    framework: str = ""

    def get_by_method(self, method: str) -> list[ApiEndpoint]:
        """Filter endpoints by HTTP method."""
        return [e for e in self.endpoints if e.method.upper() == method.upper()]

    def get_by_path_prefix(self, prefix: str) -> list[ApiEndpoint]:
        """Filter endpoints by path prefix."""
        return [e for e in self.endpoints if e.path.startswith(prefix)]


# Flask/FastAPI decorator patterns
_PY_ROUTE_DECORATORS = re.compile(
    r"@\w+\.(route|get|post|put|delete|patch|options|head)\s*\(\s*['" + '"' + r"](.+?)['" + '"' + r"]",
    re.MULTILINE,
)

# Express.js route patterns
_JS_ROUTE_PATTERN = re.compile(
    r"(?:router|app)\.(get|post|put|delete|patch|options|head)\s*\(\s*['" + '"' + r"](.+?)['" + '"' + r"]",
    re.MULTILINE,
)

# ASP.NET attribute-based routing
_CSHARP_ROUTE_ATTR = re.compile(
    r"\[Http(Get|Post|Put|Delete|Patch)\s*(?:\(\s*['" + '"' + r"](.+?)['" + '"' + r"]\s*\))?\]",
    re.MULTILINE,
)
_CSHARP_ROUTE_PREFIX = re.compile(
    r"\[Route\s*\(\s*['" + '"' + r"](.+?)['" + '"' + r"]\s*\)\]",
    re.MULTILINE,
)


class ApiMapper:
    """Detects and maps REST API endpoints across multiple frameworks."""

    def __init__(self, config: ArchAnalyzerConfig | None = None) -> None:
        self.config = config or ArchAnalyzerConfig()

    def map_endpoints(self, root: str | Path) -> ApiMap:
        """Scan the project for API endpoints and return the map."""
        root_path = Path(root)
        api_map = ApiMap()

        if not root_path.exists() or not root_path.is_dir():
            return api_map

        # Scan Python files
        for py_file in root_path.rglob("*.py"):
            if any(part in self.config.ignore_dirs for part in py_file.parts):
                continue
            endpoints = self._scan_python_file(py_file)
            api_map.endpoints.extend(endpoints)

        # Scan JavaScript/TypeScript files
        for pattern in ["*.js", "*.ts"]:
            for js_file in root_path.rglob(pattern):
                if any(part in self.config.ignore_dirs for part in js_file.parts):
                    continue
                endpoints = self._scan_js_file(js_file)
                api_map.endpoints.extend(endpoints)

        # Scan C# files
        for cs_file in root_path.rglob("*.cs"):
            if any(part in self.config.ignore_dirs for part in cs_file.parts):
                continue
            endpoints = self._scan_csharp_file(cs_file)
            api_map.endpoints.extend(endpoints)

        # Determine overall framework
        if api_map.endpoints:
            frameworks = [e.framework for e in api_map.endpoints if e.framework]
            if frameworks:
                api_map.framework = max(set(frameworks), key=frameworks.count)

        return api_map

    def scan_single_file(self, file_path: str | Path) -> list[ApiEndpoint]:
        """Scan a single file for API endpoints."""
        fpath = Path(file_path)
        if not fpath.exists():
            return []

        ext = fpath.suffix.lower()
        if ext == ".py":
            return self._scan_python_file(fpath)
        elif ext in (".js", ".ts"):
            return self._scan_js_file(fpath)
        elif ext == ".cs":
            return self._scan_csharp_file(fpath)
        return []

    def _scan_python_file(self, file_path: Path) -> list[ApiEndpoint]:
        """Scan a Python file for Flask/FastAPI route decorators."""
        endpoints: list[ApiEndpoint] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return endpoints

        content_lower = content.lower()
        framework = ""
        if "fastapi" in content_lower:
            framework = "FastAPI"
        elif "flask" in content_lower:
            framework = "Flask"
        elif "django" in content_lower:
            framework = "Django"

        for match in _PY_ROUTE_DECORATORS.finditer(content):
            method_name = match.group(1).upper()
            path = match.group(2)
            if method_name == "ROUTE":
                method_name = "GET"

            after = content[match.end():]
            func_match = re.search(r"(?:async\s+)?def\s+(\w+)", after)
            handler = func_match.group(1) if func_match else "unknown"

            line_number = content[:match.start()].count("\n") + 1

            endpoints.append(
                ApiEndpoint(
                    method=method_name,
                    path=path,
                    handler=handler,
                    source_file=str(file_path),
                    line_number=line_number,
                    framework=framework,
                )
            )

        return endpoints

    def _scan_js_file(self, file_path: Path) -> list[ApiEndpoint]:
        """Scan a JavaScript/TypeScript file for Express route definitions."""
        endpoints: list[ApiEndpoint] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return endpoints

        framework = "Express" if "express" in content.lower() else ""

        for match in _JS_ROUTE_PATTERN.finditer(content):
            method = match.group(1).upper()
            path = match.group(2)
            line_number = content[:match.start()].count("\n") + 1

            after = content[match.end():]
            handler_match = re.search(r"(\w+)\s*(?:\)|,)", after[:100])
            handler = handler_match.group(1) if handler_match else "anonymous"

            endpoints.append(
                ApiEndpoint(
                    method=method,
                    path=path,
                    handler=handler,
                    source_file=str(file_path),
                    line_number=line_number,
                    framework=framework or "Express",
                )
            )

        return endpoints

    def _scan_csharp_file(self, file_path: Path) -> list[ApiEndpoint]:
        """Scan a C# file for ASP.NET attribute-based routing."""
        endpoints: list[ApiEndpoint] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return endpoints

        route_prefix = ""
        prefix_match = _CSHARP_ROUTE_PREFIX.search(content)
        if prefix_match:
            route_prefix = prefix_match.group(1)

        class_match = re.search(r"class\s+(\w+)\s*:", content)
        controller_name = class_match.group(1) if class_match else "Unknown"

        for match in _CSHARP_ROUTE_ATTR.finditer(content):
            method = match.group(1).upper()
            sub_route = match.group(2) or ""
            full_path = f"/{route_prefix}/{sub_route}".replace("//", "/").rstrip("/") or "/"

            after = content[match.end():]
            method_match = re.search(r"(?:public|private|protected)\s+.*?\s+(\w+)\s*\(", after)
            handler = method_match.group(1) if method_match else "unknown"

            line_number = content[:match.start()].count("\n") + 1

            endpoints.append(
                ApiEndpoint(
                    method=method,
                    path=full_path,
                    handler=f"{controller_name}.{handler}",
                    source_file=str(file_path),
                    line_number=line_number,
                    framework="ASP.NET Core",
                )
            )

        return endpoints
