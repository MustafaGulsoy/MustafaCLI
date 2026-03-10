"""SAT-MAESTRO: Satellite Multidisciplinary Engineering & System Trust Officer plugin."""
from .plugin import SatMaestroPlugin

__all__ = ["SatMaestroPlugin"]


def register(registry):
    """Register SAT-MAESTRO plugin with MustafaCLI plugin registry.

    Called by directory-based plugin loader.
    """
    registry.register(SatMaestroPlugin)
