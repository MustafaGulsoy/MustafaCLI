"""
Plugin Loader - Discovery and loading from multiple sources
============================================================

Supports three discovery mechanisms:
1. Python entry_points (``mustafacli.plugins`` group)
2. Directory-based plugins (folders with ``__init__.py`` + ``register()``)
3. Convenience ``load_all_plugins`` combining all sources

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import importlib
import importlib.metadata
import sys
from pathlib import Path
from typing import Optional

from ..core.logging_config import get_logger
from .registry import PluginRegistry

logger = get_logger(__name__)

EP_GROUP = "mustafacli.plugins"


def load_entry_point_plugins(registry: PluginRegistry) -> None:
    """
    Discover and register plugins advertised via the
    ``mustafacli.plugins`` entry-point group.
    """
    try:
        eps = importlib.metadata.entry_points()
        # Python 3.12+ returns a SelectableGroups; older versions return a dict
        if hasattr(eps, "select"):
            plugin_eps = eps.select(group=EP_GROUP)
        else:
            plugin_eps = eps.get(EP_GROUP, [])
    except Exception as exc:
        logger.warning("entry_points_error", error=str(exc))
        return

    for ep in plugin_eps:
        try:
            plugin_cls = ep.load()
            registry.register(plugin_cls)
            logger.info("entry_point_plugin_loaded", name=ep.name)
        except Exception as exc:
            logger.error("entry_point_load_error", name=ep.name, error=str(exc))


def load_directory_plugins(registry: PluginRegistry, plugins_dir: str | Path) -> None:
    """
    Scan *plugins_dir* for sub-directories that contain an ``__init__.py``
    with a ``register(registry)`` callable, and invoke it.
    """
    plugins_path = Path(plugins_dir)
    if not plugins_path.is_dir():
        logger.debug("plugins_dir_missing", path=str(plugins_path))
        return

    for child in sorted(plugins_path.iterdir()):
        if not child.is_dir():
            continue
        init_file = child / "__init__.py"
        if not init_file.exists():
            continue

        module_name = f"_mustafacli_plugin_{child.name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(init_file))
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            register_fn = getattr(module, "register", None)
            if callable(register_fn):
                register_fn(registry)
                logger.info("directory_plugin_loaded", path=str(child))
            else:
                logger.warning("directory_plugin_no_register", path=str(child))
        except Exception as exc:
            logger.error("directory_plugin_error", path=str(child), error=str(exc))


def load_all_plugins(
    registry: PluginRegistry,
    personal_dir: Optional[str | Path] = None,
    project_dir: Optional[str | Path] = None,
) -> None:
    """
    Load plugins from every supported source:

    1. Entry-point group ``mustafacli.plugins``
    2. Personal plugins directory (e.g. ``~/.mustafacli/plugins``)
    3. Project-local plugins directory (e.g. ``.mustafacli/plugins``)
    """
    # 1. entry_points
    load_entry_point_plugins(registry)

    # 2. personal directory
    if personal_dir is not None:
        load_directory_plugins(registry, personal_dir)

    # 3. project directory
    if project_dir is not None:
        load_directory_plugins(registry, project_dir)

    logger.info(
        "all_plugins_loaded",
        count=len(registry.list_plugins()),
    )
