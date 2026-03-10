"""Platform compatibility layer for Windows/Linux/Mac."""
from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_mac() -> bool:
    return sys.platform == "darwin"


def get_platform_name() -> str:
    if is_windows():
        return "windows"
    elif is_mac():
        return "macos"
    return "linux"


def normalize_path(path: str) -> str:
    """Normalize path separators for current OS."""
    return str(Path(path))


def to_posix_path(path: str) -> str:
    """Convert to POSIX path (forward slashes)."""
    return Path(path).as_posix()


def get_shell_command(cmd: str) -> list[str]:
    """Get platform-appropriate shell command."""
    if is_windows():
        return ["cmd", "/c", cmd]
    return ["bash", "-c", cmd]


def get_shell_executable() -> str | None:
    """Get available shell executable."""
    if is_windows():
        for shell in ["bash", "powershell", "cmd"]:
            path = shutil.which(shell)
            if path:
                return path
        return "cmd"
    for shell in ["bash", "sh", "zsh"]:
        path = shutil.which(shell)
        if path:
            return path
    return "/bin/sh"


def get_home_dir() -> str:
    return str(Path.home())


def get_config_dir() -> str:
    """Get platform-appropriate config directory."""
    if is_windows():
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return os.path.join(appdata, "mustafacli")
        return os.path.join(get_home_dir(), ".mustafacli")
    if is_mac():
        return os.path.join(get_home_dir(), "Library", "Application Support", "mustafacli")
    # XDG on Linux
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
    if xdg_config:
        return os.path.join(xdg_config, "mustafacli")
    return os.path.join(get_home_dir(), ".config", "mustafacli")


def get_data_dir() -> str:
    """Get platform-appropriate data directory."""
    if is_windows():
        localappdata = os.environ.get("LOCALAPPDATA", "")
        if localappdata:
            return os.path.join(localappdata, "mustafacli")
        return os.path.join(get_home_dir(), ".mustafacli", "data")
    if is_mac():
        return os.path.join(get_home_dir(), "Library", "Application Support", "mustafacli", "data")
    xdg_data = os.environ.get("XDG_DATA_HOME", "")
    if xdg_data:
        return os.path.join(xdg_data, "mustafacli")
    return os.path.join(get_home_dir(), ".local", "share", "mustafacli")


def get_null_device() -> str:
    return "NUL" if is_windows() else "/dev/null"


def get_path_separator() -> str:
    return os.sep


def ensure_dir(path: str) -> str:
    """Create directory if it doesn't exist, return path."""
    Path(path).mkdir(parents=True, exist_ok=True)
    return path
