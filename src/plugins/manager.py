"""Plugin manager — install, remove, and list plugins."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .catalog import PLUGIN_CATALOG, PluginInfo

# Installed plugins state file
_STATE_FILE = Path(__file__).resolve().parent.parent.parent / ".plugins.json"


def _load_state() -> dict:
    if _STATE_FILE.exists():
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    return {"installed": []}


def _save_state(state: dict) -> None:
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_installed() -> list[str]:
    """Return names of installed plugins."""
    return _load_state().get("installed", [])


def get_catalog() -> dict[str, PluginInfo]:
    """Return the full plugin catalog."""
    return PLUGIN_CATALOG


def install_plugin(name: str, project_root: Optional[Path] = None) -> tuple[bool, str]:
    """Install a plugin by name. Returns (success, message)."""
    if name not in PLUGIN_CATALOG:
        available = ", ".join(PLUGIN_CATALOG.keys())
        return False, f"Plugin '{name}' not found. Available: {available}"

    info = PLUGIN_CATALOG[name]
    root = project_root or Path(__file__).resolve().parent.parent.parent

    # 1. Install Python dependencies (if any)
    if info.requirements_file:
        req_file = root / info.requirements_file
        if not req_file.exists():
            return False, f"Requirements file not found: {info.requirements_file}"

        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", str(req_file)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return False, f"pip install failed:\n{result.stderr[:500]}"

    # 2. Install package in editable mode (registers entry_points)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-e", str(root)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        return False, f"pip install -e failed:\n{result.stderr[:500]}"

    # 3. Append env vars to .env if not already present
    env_file = root / ".env"
    existing_env = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    new_lines = []
    for key, default in info.env_vars.items():
        if key not in existing_env:
            new_lines.append(f"{key}={default}")
    if new_lines:
        with open(env_file, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(new_lines) + "\n")

    # 4. Update state
    state = _load_state()
    if name not in state["installed"]:
        state["installed"].append(name)
    _save_state(state)

    return True, "OK"


def remove_plugin(name: str) -> tuple[bool, str]:
    """Remove a plugin from installed list."""
    state = _load_state()
    if name not in state.get("installed", []):
        return False, f"Plugin '{name}' is not installed."
    state["installed"].remove(name)
    _save_state(state)
    return True, f"Plugin '{name}' removed. Python packages were not uninstalled."
