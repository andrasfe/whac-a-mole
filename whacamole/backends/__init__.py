"""Platform accessibility backends.

Each backend exposes an AT-SPI-shaped object tree (``get_desktop()`` -> apps ->
windows -> elements, with ``get_name``/``get_role_name``/``get_state_set``/...)
so the matcher and watcher logic stays platform independent.

- Linux (Wayland & X11): AT-SPI2 via PyGObject.
- macOS: Accessibility API (AXUIElement) via PyObjC.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

IS_MACOS = sys.platform == "darwin"

_backend: Optional[Any] = None


def get_backend() -> Any:
    """Return the singleton accessibility backend for the current platform."""
    global _backend
    if _backend is None:
        if IS_MACOS:
            from whacamole.backends.macos import MacOSBackend
            _backend = MacOSBackend()
        else:
            from whacamole.backends.atspi import AtspiBackend
            _backend = AtspiBackend()
    return _backend
