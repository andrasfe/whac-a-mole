"""macOS accessibility backend (AXUIElement via PyObjC).

Wraps the macOS Accessibility API in AT-SPI-shaped adapter objects so the
matcher and watcher can traverse native, Chrome and Electron UIs unchanged.

Requires the hosting process (Terminal, iTerm, VS Code, ...) to be granted
access in System Settings > Privacy & Security > Accessibility.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import ApplicationServices as AX
import Quartz
from CoreFoundation import CFEqual, CFHash


SYSTEM_EXCLUDED_APPS = {
    "dock",
    "window server",
    "windowmanager",
    "systemuiserver",
    "control center",
    "controlcenter",
    "notification center",
    "notificationcenter",
    "spotlight",
    "loginwindow",
    "textinputmenuagent",
}

# Seconds to wait on an unresponsive application before giving up on a query.
AX_MESSAGING_TIMEOUT = 0.5

# Windows above this layer are menu bar, dock, status items, etc.
MAX_WINDOW_LAYER = 19

AX_ROLE_NAMES: Dict[str, str] = {
    "AXButton": "push button",
    "AXMenuButton": "menu button",
    "AXPopUpButton": "combo box",
    "AXCheckBox": "check box",
    "AXRadioButton": "radio button",
    "AXLink": "link",
    "AXMenuItem": "menu item",
    "AXMenuBarItem": "menu",
    "AXTabGroup": "page tab list",
    "AXWindow": "frame",
    "AXSheet": "dialog",
    "AXGroup": "panel",
    "AXStaticText": "label",
    "AXTextField": "text",
    "AXTextArea": "text",
    "AXWebArea": "document web",
    "AXScrollArea": "scroll pane",
    "AXToolbar": "tool bar",
    "AXImage": "image",
    "AXApplication": "application",
}

AX_SUBROLE_NAMES: Dict[str, str] = {
    "AXTabButton": "page tab",
    "AXToggle": "toggle button",
    "AXSwitch": "toggle button",
    "AXDialog": "dialog",
    "AXSystemDialog": "dialog",
}

ACTION_PRESS = "AXPress"

# Chromium browsers ignore AXManualAccessibility and only build their web
# content tree once AXEnhancedUserInterface is set.
CHROMIUM_BROWSERS = ("chrome", "chromium", "edge", "brave", "arc", "opera", "vivaldi")


def ax_role_to_role_name(role: str, subrole: str = "") -> str:
    """Translate an AX role/subrole pair into an AT-SPI style role name."""
    if subrole in AX_SUBROLE_NAMES:
        return AX_SUBROLE_NAMES[subrole]
    if role in AX_ROLE_NAMES:
        return AX_ROLE_NAMES[role]
    bare = role[2:] if role.startswith("AX") else role
    return re.sub(r"(?<!^)(?=[A-Z])", " ", bare).lower()


def _ax_get(element: Any, attribute: str) -> Any:
    """Read an AX attribute, returning None on any error."""
    try:
        err, value = AX.AXUIElementCopyAttributeValue(element, attribute, None)
    except Exception:
        return None
    return value if err == 0 else None


def _ax_str(element: Any, attribute: str) -> str:
    value = _ax_get(element, attribute)
    return value.strip() if isinstance(value, str) else ""


def _ax_value(value: Any, value_type: int) -> Any:
    try:
        ok, result = AX.AXValueGetValue(value, value_type, None)
        return result if ok else None
    except Exception:
        return None


@dataclass
class _State:
    value_nick: str


class _StateSet:
    def __init__(self, states: List[str]):
        self._states = [_State(s) for s in states]

    def get_states(self) -> List[_State]:
        return self._states


@dataclass
class _Rect:
    x: int
    y: int
    width: int
    height: int


class MacElement:
    """AT-SPI-shaped adapter around an AXUIElementRef."""

    def __init__(self, ref: Any, app_pid: int = 0, frontmost_pid: int = 0):
        self.ref = ref
        self.app_pid = app_pid
        self.frontmost_pid = frontmost_pid
        self._role: Optional[str] = None
        self._subrole: Optional[str] = None
        self._children: Optional[List[Any]] = None

    def __hash__(self) -> int:
        try:
            return int(CFHash(self.ref))
        except Exception:
            return id(self.ref)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MacElement):
            return NotImplemented
        try:
            return bool(CFEqual(self.ref, other.ref))
        except Exception:
            return self.ref is other.ref

    def _wrap(self, ref: Any) -> "MacElement":
        return MacElement(ref, self.app_pid, self.frontmost_pid)

    @property
    def ax_role(self) -> str:
        if self._role is None:
            self._role = _ax_str(self.ref, "AXRole")
        return self._role

    @property
    def ax_subrole(self) -> str:
        if self._subrole is None:
            self._subrole = _ax_str(self.ref, "AXSubrole")
        return self._subrole

    def get_name(self) -> str:
        name = _ax_str(self.ref, "AXTitle") or _ax_str(self.ref, "AXDescription")
        if not name and self.ax_role in ("AXButton", "AXLink", "AXMenuItem"):
            name = _ax_str(self.ref, "AXValue")
        return name

    def get_description(self) -> str:
        return _ax_str(self.ref, "AXHelp")

    def get_role_name(self) -> str:
        return ax_role_to_role_name(self.ax_role, self.ax_subrole)

    def _child_refs(self) -> List[Any]:
        if self._children is None:
            children = _ax_get(self.ref, "AXChildren")
            self._children = list(children) if children else []
        return self._children

    def get_child_count(self) -> int:
        return len(self._child_refs())

    def get_child_at_index(self, index: int) -> Optional["MacElement"]:
        children = self._child_refs()
        if 0 <= index < len(children):
            return self._wrap(children[index])
        return None

    def get_state_set(self) -> _StateSet:
        states: List[str] = []
        if self.ax_role in ("AXWindow", "AXSheet"):
            if not _ax_get(self.ref, "AXMinimized"):
                states += ["showing", "visible"]
            if self.app_pid and self.app_pid == self.frontmost_pid and (
                _ax_get(self.ref, "AXMain") or _ax_get(self.ref, "AXFocused")
            ):
                states.append("active")
            return _StateSet(states)

        if _ax_get(self.ref, "AXHidden"):
            states.append("hidden")
        else:
            states += ["showing", "visible"]
        enabled = _ax_get(self.ref, "AXEnabled")
        if enabled is None or enabled:
            states += ["enabled", "sensitive"]
        else:
            # e.g. stale "Allow" buttons left in a web chat history
            states.append("disabled")
        if _ax_get(self.ref, "AXFocused"):
            states.append("focused")
        return _StateSet(states)

    def get_extents(self, coord_type: int = 0) -> _Rect:
        # AX screen coordinates are top-left based, matching CGEvent coordinates.
        pos = _ax_value(_ax_get(self.ref, "AXPosition"), AX.kAXValueCGPointType)
        size = _ax_value(_ax_get(self.ref, "AXSize"), AX.kAXValueCGSizeType)
        if pos is None or size is None:
            return _Rect(0, 0, 0, 0)
        return _Rect(int(pos.x), int(pos.y), int(size.width), int(size.height))

    def get_attributes(self) -> Dict[str, str]:
        attrs: Dict[str, str] = {"toolkit": "cocoa"}
        if self.ax_subrole:
            attrs["subrole"] = self.ax_subrole
        role_desc = _ax_str(self.ref, "AXRoleDescription")
        if role_desc:
            attrs["role-description"] = role_desc
        # Chromium / Electron / WebKit expose the DOM class list and id.
        classes = _ax_get(self.ref, "AXDOMClassList")
        if classes:
            attrs["class"] = " ".join(str(c) for c in classes)
        dom_id = _ax_str(self.ref, "AXDOMIdentifier")
        if dom_id:
            attrs["id"] = dom_id
        # Native default buttons (the blue "return key" button) are primary actions.
        if self.ax_role == "AXButton" and self._is_default_button():
            attrs["style"] = "default primary suggested-action"
        return attrs

    def _is_default_button(self) -> bool:
        window = _ax_get(self.ref, "AXWindow")
        if window is None:
            return False
        default = _ax_get(window, "AXDefaultButton")
        if default is None:
            return False
        try:
            return bool(CFEqual(default, self.ref))
        except Exception:
            return False

    def _action_names(self) -> List[str]:
        try:
            err, names = AX.AXUIElementCopyActionNames(self.ref, None)
        except Exception:
            return []
        return list(names) if err == 0 and names else []

    def get_n_actions(self) -> int:
        return len(self._action_names())

    def do_action(self, index: int) -> bool:
        names = self._action_names()
        if not names:
            return False
        # Index 0 maps to the press action, mirroring AT-SPI's "click" action.
        action = ACTION_PRESS if index == 0 and ACTION_PRESS in names else names[min(index, len(names) - 1)]
        try:
            return AX.AXUIElementPerformAction(self.ref, action) == 0
        except Exception:
            return False


class MacApplication(MacElement):
    """Application node whose children are its AX windows."""

    def __init__(self, pid: int, name: str, frontmost_pid: int):
        super().__init__(AX.AXUIElementCreateApplication(pid), pid, frontmost_pid)
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_role_name(self) -> str:
        return "application"

    def _child_refs(self) -> List[Any]:
        if self._children is None:
            windows = _ax_get(self.ref, "AXWindows")
            self._children = list(windows) if windows else []
        return self._children


class MacDesktop:
    """Desktop root listing applications that currently have on-screen windows."""

    def __init__(self, apps: List[MacApplication]):
        self._apps = apps

    def get_child_count(self) -> int:
        return len(self._apps)

    def get_child_at_index(self, index: int) -> Optional[MacApplication]:
        return self._apps[index] if 0 <= index < len(self._apps) else None


class MacOSBackend:
    """Accessibility backend backed by the macOS Accessibility API."""

    name = "macos"
    system_excluded_apps = SYSTEM_EXCLUDED_APPS

    def __init__(self) -> None:
        self._own_pid = os.getpid()
        self._web_a11y_enabled: set = set()
        self._system_wide = AX.AXUIElementCreateSystemWide()
        # A timeout on the system-wide element applies to every element.
        try:
            AX.AXUIElementSetMessagingTimeout(self._system_wide, AX_MESSAGING_TIMEOUT)
        except Exception:
            pass

    def init(self) -> Optional[str]:
        """Check (and prompt for) Accessibility permission. Returns a warning, if any."""
        try:
            options = {AX.kAXTrustedCheckOptionPrompt: True}
            trusted = AX.AXIsProcessTrustedWithOptions(options)
        except Exception:
            trusted = AX.AXIsProcessTrusted()
        if not trusted:
            return (
                "Accessibility permission not granted. Enable your terminal/Python in "
                "System Settings > Privacy & Security > Accessibility, then restart."
            )
        return None

    def _focused_app_pid(self) -> int:
        app = _ax_get(self._system_wide, "AXFocusedApplication")
        if app is None:
            return 0
        try:
            err, pid = AX.AXUIElementGetPid(app, None)
            return int(pid) if err == 0 else 0
        except Exception:
            return 0

    def _on_screen_apps(self) -> Tuple[Dict[int, str], int]:
        """Map pid -> owner name for apps with on-screen windows, plus the frontmost pid.

        Uses CGWindowList rather than NSWorkspace, which goes stale without a
        running Cocoa run loop (e.g. in headless / background-thread mode).
        The list is ordered front to back, so the owner of the first normal
        window is the frontmost app (AXFocusedApplication is often stale or fails).
        """
        options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        infos = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
        apps: Dict[int, str] = {}
        frontmost = 0
        for info in infos:
            try:
                layer = int(info.get("kCGWindowLayer", 0))
                pid = int(info["kCGWindowOwnerPID"])
            except Exception:
                continue
            if layer > MAX_WINDOW_LAYER:
                continue
            if not frontmost and layer == 0:
                frontmost = pid
            if pid == self._own_pid or pid in apps:
                continue
            apps[pid] = str(info.get("kCGWindowOwnerName") or "")
        return apps, frontmost

    def _enable_web_accessibility(self, app: MacApplication) -> None:
        """Ask Chromium/Electron apps to expose their web content tree (once per pid)."""
        if app.app_pid in self._web_a11y_enabled:
            return
        self._web_a11y_enabled.add(app.app_pid)
        try:
            err = AX.AXUIElementSetAttributeValue(app.ref, "AXManualAccessibility", True)
            if err != 0 and any(b in app.get_name().lower() for b in CHROMIUM_BROWSERS):
                AX.AXUIElementSetAttributeValue(app.ref, "AXEnhancedUserInterface", True)
        except Exception:
            pass

    def get_desktop(self) -> MacDesktop:
        on_screen, frontmost_window_pid = self._on_screen_apps()
        frontmost = frontmost_window_pid or self._focused_app_pid()
        apps: List[MacApplication] = []
        for pid, name in on_screen.items():
            app = MacApplication(pid, name, frontmost)
            self._enable_web_accessibility(app)
            apps.append(app)
        # Frontmost first so the active window wins ties.
        apps.sort(key=lambda a: a.app_pid != frontmost)
        return MacDesktop(apps)

    def mouse_click(self, x: int, y: int) -> bool:
        """Move to (x, y) and post a left click via Quartz events."""
        point = Quartz.CGPointMake(x, y)
        button = Quartz.kCGMouseButtonLeft
        for event_type, pause in (
            (Quartz.kCGEventMouseMoved, 0.02),
            (Quartz.kCGEventLeftMouseDown, 0.05),
            (Quartz.kCGEventLeftMouseUp, 0.0),
        ):
            event = Quartz.CGEventCreateMouseEvent(None, event_type, point, button)
            if event is None:
                return False
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            if pause:
                time.sleep(pause)
        return True

    def raise_window(self, window: Any) -> None:
        ref = getattr(window, "ref", None)
        if ref is None:
            return
        AX.AXUIElementPerformAction(ref, "AXRaise")
        app_ref = AX.AXUIElementCreateApplication(window.app_pid)
        AX.AXUIElementSetAttributeValue(app_ref, "AXFrontmost", True)

    def notify(self, title: str, body: str) -> None:
        """Post a Notification Center banner via osascript asynchronously."""
        script = f"display notification {_applescript_str(body)} with title {_applescript_str(title)}"
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _applescript_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


TEST_DIALOG_TITLE = "Permission Request (Test Window)"


def open_native_test_dialog(wait: bool = True) -> Optional[str]:
    """Show a native macOS permission dialog with a blue default "Allow" button.

    GTK widgets are not exposed to the macOS Accessibility API, so the test
    dialog on macOS is a native AppKit alert driven by osascript.
    Returns the clicked button name when ``wait`` is True.
    """
    script = (
        "activate\n"
        f"display dialog {_applescript_str('Example App would like to access your camera and microphone.')} "
        f"with title {_applescript_str(TEST_DIALOG_TITLE)} "
        'buttons {"Cancel", "Don\'t Allow", "Allow"} default button "Allow" cancel button "Cancel" '
        "giving up after 120"
    )
    cmd = ["osascript", "-e", script]
    if not wait:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return None
    proc = subprocess.run(cmd, capture_output=True, text=True)
    match = re.search(r"button returned:([^,]*)", proc.stdout)
    if match:
        return match.group(1).strip() or None
    return "Cancel" if proc.returncode != 0 else None
