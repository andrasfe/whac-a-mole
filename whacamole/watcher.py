"""Active window button watcher and click execution engine."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib

from whacamole.config import WatcherConfig
from whacamole.matcher import ButtonMatcher, MatchResult


def ensure_accessibility_enabled() -> None:
    """Ensure GNOME/Chromium accessibility features are active so browser DOMs are exposed."""
    try:
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.a11y.applications", "screen-reader-enabled", "true"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
    except Exception:
        pass


@dataclass
class WindowInfo:
    """Information about an application window."""
    app_name: str
    window_title: str
    accessible: Atspi.Accessible
    is_active: bool


class WindowWatcher:
    """Watches the active window for matching buttons and executes clicks."""

    def __init__(self, config: Optional[WatcherConfig] = None):
        self.config = config or WatcherConfig()
        self.matcher = ButtonMatcher(self.config)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._glib_source_id: Optional[int] = None

        # State tracking
        self.current_window: Optional[Tuple[str, str]] = None
        self._window_click_counts: Dict[str, int] = {}
        self._last_click_times: Dict[str, float] = {}

        # Callbacks
        self.on_status_changed: Optional[Callable[[bool, str], None]] = None
        self.on_window_changed: Optional[Callable[[str, str], None]] = None
        self.on_button_detected: Optional[Callable[[MatchResult, str, str], None]] = None
        self.on_button_clicked: Optional[Callable[[MatchResult, str, str, bool, str], None]] = None
        self.on_log: Optional[Callable[[str, str], None]] = None

    @property
    def is_running(self) -> bool:
        """Return True if watcher is actively running."""
        return self._running

    def update_config(self, config: WatcherConfig) -> None:
        """Update active configuration."""
        self.config = config
        self.matcher.update_config(config)
        self._log("Configuration updated", "INFO")

    def _log(self, message: str, level: str = "INFO") -> None:
        """Emit log message."""
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level}] {message}"
        if self.on_log:
            try:
                self.on_log(formatted, level)
            except Exception:
                pass
        else:
            print(formatted)

    def start(self, use_glib_timer: bool = False) -> None:
        """Start the watcher.

        Args:
            use_glib_timer: If True, uses GLib.timeout_add (recommended when GTK main loop is active).
                            If False, uses a background daemon thread.
        """
        if self._running:
            return

        ensure_accessibility_enabled()

        self._running = True
        self._stop_event.clear()

        if use_glib_timer:
            interval_ms = int(max(0.1, self.config.poll_interval_sec) * 1000)
            self._glib_source_id = GLib.timeout_add(interval_ms, self._glib_poll_callback)
        else:
            self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="WhacamoleWatcher")
            self._thread.start()

        if self.on_status_changed:
            self.on_status_changed(True, "Watching active window...")
        self._log(f"Started watcher (target text: '{self.config.target_text}', color: '{self.config.target_color}', mode: '{self.config.color_mode}')", "INFO")

    def stop(self) -> None:
        """Stop watching."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._glib_source_id is not None:
            GLib.source_remove(self._glib_source_id)
            self._glib_source_id = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

        if self.on_status_changed:
            self.on_status_changed(False, "Stopped")
        self._log("Stopped watcher", "INFO")

    def _glib_poll_callback(self) -> bool:
        """GLib timer callback."""
        if not self._running:
            return False
        try:
            self.scan_and_act()
        except Exception as e:
            self._log(f"Error during scan: {e}", "ERROR")
        return True

    def _worker_loop(self) -> None:
        """Background thread worker loop."""
        while self._running and not self._stop_event.is_set():
            try:
                self.scan_and_act()
            except Exception as e:
                self._log(f"Error during scan: {e}", "ERROR")
            interval = max(0.1, self.config.poll_interval_sec)
            self._stop_event.wait(interval)

    def get_active_window(self) -> Optional[WindowInfo]:
        """Find the active window (or primary target window)."""
        targets = self.get_target_windows()
        for win in targets:
            if win.is_active:
                return win
        return targets[0] if targets else None

    def get_target_windows(self) -> List[WindowInfo]:
        """Find windows matching the watcher configuration.

        If tab_title_substring is set:
            Searches all windows whose title or browser tab matches the substring,
            whether active or in the background (unless require_focus is True).
        If tab_title_substring is empty:
            If require_focus is True: returns only the currently active window.
            If require_focus is False: returns the active window followed by open visible windows.
        """
        targets: List[WindowInfo] = []
        try:
            desktop = Atspi.get_desktop(0)
            if not desktop:
                return []

            sub_filter = (self.config.tab_title_substring or self.config.window_title_filter or "").strip()
            require_focus = self.config.require_focus

            app_count = desktop.get_child_count()
            for i in range(app_count):
                app = desktop.get_child_at_index(i)
                if not app:
                    continue

                app_name = app.get_name() or "Unknown"
                win_count = app.get_child_count()
                for j in range(win_count):
                    win = app.get_child_at_index(j)
                    if not win:
                        continue

                    try:
                        state_set = win.get_state_set()
                        states = {s.value_nick for s in state_set.get_states()}
                        if "showing" not in states and "visible" not in states:
                            continue

                        is_active = "active" in states

                        # If focus is strictly required, skip unfocused windows
                        if require_focus and not is_active:
                            continue

                        # If no tab/window substring is configured, only watch active window
                        if not sub_filter and not is_active:
                            continue

                        win_title = win.get_name() or ""

                        # Check window exclusions (self, etc.)
                        if self._is_window_excluded(win_title, app_name):
                            continue

                        # Check tab/window title substring filter if configured
                        if sub_filter:
                            if not self._window_or_tab_matches(win, win_title, sub_filter):
                                continue

                        win_info = WindowInfo(
                            app_name=app_name,
                            window_title=win_title,
                            accessible=win,
                            is_active=is_active,
                        )

                        # Prioritize active window
                        if is_active:
                            targets.insert(0, win_info)
                        else:
                            targets.append(win_info)

                    except Exception:
                        continue
        except Exception as e:
            self._log(f"Failed to query windows: {e}", "DEBUG")

        return targets

    def _window_or_tab_matches(self, win: Atspi.Accessible, win_title: str, substring: str) -> bool:
        """Check if window title or any child tab matches the substring."""
        if not substring:
            return True
        sub_lower = substring.lower()
        if sub_lower in win_title.lower():
            return True

        # Check child page tab elements (e.g. browser tabs in Chrome/Firefox)
        try:
            def check_tabs(obj: Atspi.Accessible, depth: int = 0) -> bool:
                if depth > 12 or obj is None:
                    return False
                try:
                    role = (obj.get_role_name() or "").lower()
                    if "tab" in role:
                        t_name = (obj.get_name() or "").lower()
                        if sub_lower in t_name:
                            return True
                except Exception:
                    pass

                try:
                    child_count = obj.get_child_count()
                    for c in range(child_count):
                        ch = obj.get_child_at_index(c)
                        if ch and check_tabs(ch, depth + 1):
                            return True
                except Exception:
                    pass
                return False

            return check_tabs(win)
        except Exception:
            return False

    def _is_window_excluded(self, win_title: str, app_name: str) -> bool:
        """Check if window or app is excluded."""
        lower_title = win_title.lower()
        lower_app = app_name.lower()

        for excluded in self.config.exclude_windows:
            ex_lower = excluded.lower()
            if ex_lower in lower_title or ex_lower in lower_app:
                return True

        return False

    def scan_window_buttons(
        self, window_obj: Atspi.Accessible, max_depth: Optional[int] = None
    ) -> List[MatchResult]:
        """Traverse window accessibility hierarchy and find all matching buttons."""
        if max_depth is None:
            max_depth = getattr(self.config, "max_traversal_depth", 60)

        matches: List[MatchResult] = []
        visited: Set[int] = set()

        def traverse(obj: Atspi.Accessible, depth: int) -> None:
            if depth > max_depth or obj is None or len(visited) > 10000:
                return

            try:
                obj_id = hash(obj)
                if obj_id in visited:
                    return
                visited.add(obj_id)
            except Exception:
                pass

            # Evaluate current element
            try:
                result = self.matcher.evaluate(obj)
                if result.matched:
                    matches.append(result)
            except Exception:
                pass

            # Recurse into children
            try:
                child_count = obj.get_child_count()
                for i in range(child_count):
                    child = obj.get_child_at_index(i)
                    if child:
                        traverse(child, depth + 1)
            except Exception:
                pass

        traverse(window_obj, 0)
        # Sort by score descending (so highest score / preferred color is first)
        matches.sort(key=lambda r: r.score, reverse=True)
        return matches

    def scan_and_act(self) -> None:
        """Execute a scan of target windows and click button if present."""
        target_windows = self.get_target_windows()
        if not target_windows:
            return

        for win_info in target_windows:
            window_key = f"{win_info.app_name}::{win_info.window_title}"
            current_pair = (win_info.app_name, win_info.window_title)

            if win_info.is_active and self.current_window != current_pair:
                self.current_window = current_pair
                if self.on_window_changed:
                    self.on_window_changed(win_info.app_name, win_info.window_title)
                self._log(f"Active window: [{win_info.app_name}] \"{win_info.window_title}\"", "DEBUG")
            elif not win_info.is_active and self.config.tab_title_substring:
                if self.current_window != current_pair:
                    self.current_window = current_pair
                    if self.on_window_changed:
                        self.on_window_changed(win_info.app_name, f"{win_info.window_title} (Background)")
                    self._log(f"Target window (Background): [{win_info.app_name}] \"{win_info.window_title}\"", "DEBUG")

            # Check cooldown & click limits for this window
            now = time.time()
            last_time = self._last_click_times.get(window_key, 0.0)
            click_count = self._window_click_counts.get(window_key, 0)

            if self.config.max_clicks_per_window > 0 and click_count >= self.config.max_clicks_per_window:
                continue

            if (now - last_time) < self.config.cooldown_sec:
                continue

            # Find matching buttons in this target window
            matches = self.scan_window_buttons(win_info.accessible)
            if not matches:
                continue

            best_match = matches[0]
            if self.on_button_detected:
                self.on_button_detected(best_match, win_info.app_name, win_info.window_title)

            # Execute click on target
            self._execute_click(best_match, win_info, window_key)
            # Break after executing one click per poll cycle
            break

    def _execute_click(self, match: MatchResult, win_info: WindowInfo, window_key: str) -> None:
        """Execute click on matched button."""
        now = time.time()
        self._last_click_times[window_key] = now
        self._window_click_counts[window_key] = self._window_click_counts.get(window_key, 0) + 1

        bg_tag = "" if win_info.is_active else " [Background]"
        details = f"button '{match.text}' (role={match.role}, score={match.score:.0f}) in window '{win_info.window_title}'{bg_tag}"

        if self.config.dry_run:
            self._log(f"[SIMULATION] Would click {details}", "INFO")
            if self.on_button_clicked:
                self.on_button_clicked(match, win_info.app_name, win_info.window_title, True, "simulation")
            return

        # Pre-click delay
        if self.config.click_delay_sec > 0:
            time.sleep(self.config.click_delay_sec)

        # Optional auto-raise for background windows if mouse clicking is required
        if not win_info.is_active and self.config.auto_raise_window:
            try:
                if hasattr(win_info.accessible, "get_component"):
                    comp = win_info.accessible.get_component()
                    if comp and hasattr(comp, "grab_focus"):
                        comp.grab_focus()
            except Exception:
                pass

        success = False
        method_used = self.config.click_method

        # 1. Native AT-SPI action
        if self.config.click_method in ("action", "both"):
            try:
                if hasattr(match.element, "get_n_actions") and match.element.get_n_actions() > 0:
                    action_res = match.element.do_action(0)
                    if action_res:
                        success = True
            except Exception as e:
                self._log(f"AT-SPI action failed: {e}", "DEBUG")

        # 2. Simulated mouse event
        if self.config.click_method in ("mouse", "both") or (not success and self.config.click_method == "action"):
            cx, cy = match.center
            if cx > 0 and cy > 0:
                try:
                    # Move to button center, press button 1, hold briefly, release
                    Atspi.generate_mouse_event(cx, cy, "abs")
                    time.sleep(0.02)
                    p_res = Atspi.generate_mouse_event(cx, cy, "b1p")
                    time.sleep(0.05)
                    r_res = Atspi.generate_mouse_event(cx, cy, "b1r")
                    if p_res or r_res:
                        success = True
                        if self.config.click_method == "both":
                            method_used = "both (action + mouse)"
                        else:
                            method_used = "mouse"
                except Exception as e:
                    self._log(f"Mouse event failed: {e}", "DEBUG")

        if success:
            self._log(f"Clicked {details} via {method_used}", "INFO")
        else:
            self._log(f"Attempted click on {details} but action returned False", "WARN")

        # Notify callbacks
        if self.on_button_clicked:
            self.on_button_clicked(match, win_info.app_name, win_info.window_title, success, method_used)

        # Desktop notification
        if self.config.desktop_notifications and success:
            self._send_desktop_notification(match.text, win_info.window_title)

        # Sound alert
        if self.config.sound_alert and success:
            self._emit_sound()

    def _send_desktop_notification(self, button_text: str, window_title: str) -> None:
        """Send desktop notification via notify-send asynchronously."""
        title = "Whac-A-Mole Auto-Clicker"
        body = f"Clicked '{button_text}' in:\n{window_title}"
        try:
            subprocess.Popen(
                ["notify-send", "-a", "Whac-A-Mole", "-i", "emblem-default", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _emit_sound(self) -> None:
        """Emit terminal or system beep."""
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass
