"""Linux AT-SPI2 accessibility backend (Wayland & X11)."""

from __future__ import annotations

import subprocess
import time
from typing import Any, Optional

import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi


SYSTEM_EXCLUDED_APPS = {
    "gnome-shell",
    "mutter",
    "gjs",
    "desktop-icons",
    "at-spi2-registryd",
    "systemd",
    "ibus-x11",
    "ibus-daemon",
    "pipewire",
}


def ensure_accessibility_enabled() -> None:
    """Ensure GNOME toolkit accessibility is active without launching a screen reader."""
    try:
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.interface", "toolkit-accessibility", "true"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
    except Exception:
        pass


class AtspiBackend:
    """Accessibility backend backed by the Linux AT-SPI2 bus."""

    name = "atspi"
    system_excluded_apps = SYSTEM_EXCLUDED_APPS

    def init(self) -> Optional[str]:
        """Prepare the accessibility bus. Returns a warning message, if any."""
        ensure_accessibility_enabled()
        try:
            Atspi.init()
        except Exception:
            pass
        return None

    def get_desktop(self) -> Any:
        return Atspi.get_desktop(0)

    def mouse_click(self, x: int, y: int) -> bool:
        """Move to (x, y), press button 1, hold briefly, release."""
        Atspi.generate_mouse_event(x, y, "abs")
        time.sleep(0.02)
        p_res = Atspi.generate_mouse_event(x, y, "b1p")
        time.sleep(0.05)
        r_res = Atspi.generate_mouse_event(x, y, "b1r")
        return bool(p_res or r_res)

    def raise_window(self, window: Any) -> None:
        if hasattr(window, "get_component"):
            comp = window.get_component()
            if comp and hasattr(comp, "grab_focus"):
                comp.grab_focus()

    def notify(self, title: str, body: str) -> None:
        """Send desktop notification via notify-send asynchronously."""
        subprocess.Popen(
            ["notify-send", "-a", "Whac-A-Mole", "-i", "emblem-default", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
