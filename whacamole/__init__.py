"""Whac-A-Mole: Intelligent active-window button watcher and auto-clicker.

Monitors the active window for target buttons (e.g., blue 'Allow' buttons)
with fully configurable text, color, style, and behavior.
"""

__version__ = "1.0.0"

# Initialize D-Bus thread safety so AT-SPI calls from threads don't corrupt connection state
try:
    import ctypes
    _libdbus = ctypes.CDLL("libdbus-1.so.3")
    _libdbus.dbus_threads_init_default()
except Exception:
    pass
