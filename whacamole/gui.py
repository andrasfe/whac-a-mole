"""Graphical User Interface for Whac-A-Mole using native GTK3."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Optional

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from whacamole.backends import IS_MACOS
from whacamole.config import DEFAULT_CONFIG_FILE, WatcherConfig
from whacamole.matcher import MatchResult
from whacamole.test_dialog import TestDialog
from whacamole.watcher import WindowWatcher


GUI_CSS = b"""
window.whac-main {
    background-color: #f6f8fa;
}

headerbar {
    border-bottom: 1px solid #d0d7de;
}

box.card {
    background-color: #ffffff;
    border-radius: 8px;
    border: 1px solid #d0d7de;
    padding: 14px;
}

label.card-title {
    font-size: 13px;
    font-weight: bold;
    color: #57606a;
}

label.active-win-app {
    font-size: 15px;
    font-weight: bold;
    color: #1f2328;
}

label.active-win-title {
    font-size: 13px;
    color: #57606a;
}

label.status-badge-active {
    background-color: #dafbe1;
    color: #1a7f37;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #aceebb;
}

label.status-badge-stopped {
    background-color: #f6f8fa;
    color: #57606a;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #d0d7de;
}

button.start-btn {
    background: #1f883d;
    color: #ffffff;
    font-weight: bold;
    border-radius: 6px;
    border: none;
    padding: 6px 16px;
}

button.stop-btn {
    background: #cf222e;
    color: #ffffff;
    font-weight: bold;
    border-radius: 6px;
    border: none;
    padding: 6px 16px;
}

button.target-preview-btn {
    padding: 8px 24px;
    border-radius: 6px;
    font-weight: bold;
    font-size: 14px;
}

textview.log-view {
    font-family: monospace;
    font-size: 12px;
    background-color: #1e1e1e;
    color: #d4d4d4;
    border-radius: 6px;
}
"""


class WhacamoleWindow(Gtk.Window):
    """Main Application Window for Whac-A-Mole."""

    def __init__(self, config: Optional[WatcherConfig] = None):
        super().__init__(title="Whac-A-Mole - Active Window Button Watcher")
        self.set_default_size(780, 640)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class("whac-main")

        self.config = config or WatcherConfig.load_from_file()
        self.watcher = WindowWatcher(self.config)

        # Statistics
        self.stat_windows_monitored = 0
        self.stat_buttons_detected = 0
        self.stat_clicks_executed = 0

        # Sub-dialog references
        self._test_dialog: Optional[TestDialog] = None

        self._load_css()
        self._build_header_bar()
        self._build_ui()
        self._connect_watcher_signals()

        # Update preview badge
        self._update_preview_badge()

        # Auto-start if configured
        if self.config.auto_start:
            GLib.idle_add(self._on_start_clicked, None)

    def _load_css(self) -> None:
        screen = Gdk.Screen.get_default()
        if screen is None:
            return
        provider = Gtk.CssProvider()
        try:
            provider.load_from_data(GUI_CSS)
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        except Exception:
            pass

    def _build_header_bar(self) -> None:
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("Whac-A-Mole")
        header.set_subtitle("Watches active window for target buttons and clicks them")

        # Test window launcher button
        test_btn = Gtk.Button(label="Open Test Dialog")
        test_btn.set_tooltip_text("Launch sample window with blue Allow button to test auto-clicker")
        test_btn.connect("clicked", self._on_launch_test_dialog)
        header.pack_start(test_btn)

        # Status badge
        self.status_badge = Gtk.Label(label="PAUSED")
        self.status_badge.get_style_context().add_class("status-badge-stopped")
        header.pack_end(self.status_badge)

        # Start/Stop Watcher Button
        self.toggle_watch_btn = Gtk.Button(label="Start Watcher")
        self.toggle_watch_btn.get_style_context().add_class("start-btn")
        self.toggle_watch_btn.connect("clicked", self._on_toggle_watcher)
        header.pack_end(self.toggle_watch_btn)

        self.set_titlebar(header)

    def _build_ui(self) -> None:
        notebook = Gtk.Notebook()
        notebook.set_margin_start(12)
        notebook.set_margin_end(12)
        notebook.set_margin_top(12)
        notebook.set_margin_bottom(12)

        # Tab 1: Monitor & Dashboard
        monitor_page = self._build_monitor_tab()
        notebook.append_page(monitor_page, Gtk.Label(label="Dashboard & Monitor"))

        # Tab 2: Settings & Rules
        config_page = self._build_config_tab()
        notebook.append_page(config_page, Gtk.Label(label="Button Configuration"))

        self.add(notebook)

    def _build_monitor_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        # Tab / Substring Filter Card
        tab_filter_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        tab_filter_card.get_style_context().add_class("card")

        filter_lbl = Gtk.Label(label="Target Tab / Window Title:", xalign=0.0)
        filter_lbl.get_style_context().add_class("card-title")

        self.entry_quick_tab = Gtk.Entry(text=self.config.tab_title_substring)
        self.entry_quick_tab.set_placeholder_text("Substring to match (e.g. 'Permissions', 'Meet', 'OAuth'). Empty matches all.")
        self.entry_quick_tab.set_tooltip_text("When set, auto-clicks target button in this tab/window even when it loses focus!")
        self.entry_quick_tab.connect("changed", self._on_quick_tab_changed)

        focus_lbl = Gtk.Label(label="Require Focus:", xalign=0.0)
        focus_lbl.get_style_context().add_class("card-title")
        self.switch_quick_focus = Gtk.Switch(active=self.config.require_focus)
        self.switch_quick_focus.set_tooltip_text("OFF (recommended): clicks matching buttons in background when focus is lost. ON: active focus only.")
        self.switch_quick_focus.connect("notify::active", self._on_quick_focus_changed)

        tab_filter_card.pack_start(filter_lbl, False, False, 0)
        tab_filter_card.pack_start(self.entry_quick_tab, True, True, 0)
        tab_filter_card.pack_start(focus_lbl, False, False, 0)
        tab_filter_card.pack_start(self.switch_quick_focus, False, False, 0)
        vbox.pack_start(tab_filter_card, False, False, 0)

        # Top row: Active Window Card & Target Button Card
        top_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        top_hbox.set_homogeneous(True)

        # Card 1: Active Window
        win_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        win_card.get_style_context().add_class("card")
        win_title_lbl = Gtk.Label(label="CURRENT ACTIVE WINDOW")
        win_title_lbl.get_style_context().add_class("card-title")
        win_title_lbl.set_xalign(0.0)

        self.lbl_app_name = Gtk.Label(label="None")
        self.lbl_app_name.get_style_context().add_class("active-win-app")
        self.lbl_app_name.set_xalign(0.0)

        self.lbl_win_title = Gtk.Label(label="Waiting for active window focus...")
        self.lbl_win_title.get_style_context().add_class("active-win-title")
        self.lbl_win_title.set_xalign(0.0)
        self.lbl_win_title.set_line_wrap(True)

        win_card.pack_start(win_title_lbl, False, False, 0)
        win_card.pack_start(self.lbl_app_name, False, False, 0)
        win_card.pack_start(self.lbl_win_title, False, False, 0)
        top_hbox.pack_start(win_card, True, True, 0)

        # Card 2: Target Button Preview & Stats
        target_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        target_card.get_style_context().add_class("card")
        target_title_lbl = Gtk.Label(label="TARGET BUTTON SPECIFICATION")
        target_title_lbl.get_style_context().add_class("card-title")
        target_title_lbl.set_xalign(0.0)

        preview_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        preview_box.set_halign(Gtk.Align.START)
        preview_box.set_valign(Gtk.Align.CENTER)

        self.preview_btn = Gtk.Button(label=self.config.target_text)
        self.preview_btn.get_style_context().add_class("target-preview-btn")
        self.preview_btn.set_sensitive(False)  # visual only

        self.lbl_target_info = Gtk.Label(label="Style: Blue / Suggested Action\nMode: Prefer Match")
        self.lbl_target_info.set_xalign(0.0)

        preview_box.pack_start(self.preview_btn, False, False, 0)
        preview_box.pack_start(self.lbl_target_info, True, True, 0)

        # Stats bar
        self.lbl_stats = Gtk.Label(label="Windows: 0 | Buttons Found: 0 | Clicks Executed: 0")
        self.lbl_stats.set_xalign(0.0)

        target_card.pack_start(target_title_lbl, False, False, 0)
        target_card.pack_start(preview_box, True, True, 0)
        target_card.pack_start(self.lbl_stats, False, False, 0)
        top_hbox.pack_start(target_card, True, True, 0)

        vbox.pack_start(top_hbox, False, False, 0)

        # Log Section
        log_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        log_card.get_style_context().add_class("card")

        log_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        log_title = Gtk.Label(label="ACTIVITY & CLICK LOG")
        log_title.get_style_context().add_class("card-title")
        log_title.set_xalign(0.0)

        clear_btn = Gtk.Button(label="Clear Log")
        clear_btn.connect("clicked", self._on_clear_log)

        log_header.pack_start(log_title, True, True, 0)
        log_header.pack_end(clear_btn, False, False, 0)
        log_card.pack_start(log_header, False, False, 0)

        # Scrolled Text View
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_min_content_height(250)

        self.log_buffer = Gtk.TextBuffer()
        self.log_view = Gtk.TextView(buffer=self.log_buffer)
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.get_style_context().add_class("log-view")
        self.log_view.set_left_margin(10)
        self.log_view.set_right_margin(10)
        self.log_view.set_top_margin(10)
        self.log_view.set_bottom_margin(10)

        scrolled.add(self.log_view)
        log_card.pack_start(scrolled, True, True, 0)

        vbox.pack_start(log_card, True, True, 0)
        return vbox

    def _build_config_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)

        # 1. Text Matching Group
        text_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        text_card.get_style_context().add_class("card")
        g1_title = Gtk.Label(label="1. BUTTON TEXT MATCHING")
        g1_title.get_style_context().add_class("card-title")
        g1_title.set_xalign(0.0)
        text_card.pack_start(g1_title, False, False, 0)

        grid1 = Gtk.Grid(column_spacing=12, row_spacing=8)

        # Target text
        grid1.attach(Gtk.Label(label="Target Text:", xalign=0.0), 0, 0, 1, 1)
        self.entry_target_text = Gtk.Entry(text=self.config.target_text)
        self.entry_target_text.connect("changed", self._on_config_control_changed)
        grid1.attach(self.entry_target_text, 1, 0, 2, 1)

        # Match mode
        grid1.attach(Gtk.Label(label="Matching Mode:", xalign=0.0), 0, 1, 1, 1)
        self.combo_match_mode = Gtk.ComboBoxText()
        self.combo_match_mode.append("contains", "Contains (Substring, e.g. 'Allow' or 'Always Allow')")
        self.combo_match_mode.append("exact", "Exact match ('Allow' only)")
        self.combo_match_mode.append("regex", "Regular Expression pattern")
        self.combo_match_mode.set_active_id(self.config.text_match_mode)
        self.combo_match_mode.connect("changed", self._on_config_control_changed)
        grid1.attach(self.combo_match_mode, 1, 1, 2, 1)

        # Case sensitive
        grid1.attach(Gtk.Label(label="Case Sensitive:", xalign=0.0), 0, 2, 1, 1)
        self.switch_case = Gtk.Switch(active=self.config.case_sensitive)
        self.switch_case.connect("notify::active", self._on_config_control_changed)
        grid1.attach(self.switch_case, 1, 2, 1, 1)

        text_card.pack_start(grid1, False, False, 0)
        vbox.pack_start(text_card, False, False, 0)

        # 2. Color & Style Group
        color_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        color_card.get_style_context().add_class("card")
        g2_title = Gtk.Label(label="2. BUTTON COLOR & STYLE CONFIGURATION")
        g2_title.get_style_context().add_class("card-title")
        g2_title.set_xalign(0.0)
        color_card.pack_start(g2_title, False, False, 0)

        grid2 = Gtk.Grid(column_spacing=12, row_spacing=8)

        # Target Color
        grid2.attach(Gtk.Label(label="Target Color:", xalign=0.0), 0, 0, 1, 1)
        self.combo_color = Gtk.ComboBoxText()
        self.combo_color.append("blue", "Blue (Primary / Suggested Action / #007bff)")
        self.combo_color.append("green", "Green (Success / #28a745)")
        self.combo_color.append("red", "Red (Danger / #dc3545)")
        self.combo_color.append("orange", "Orange (Warning / #ffc107)")
        self.combo_color.append("custom", "Custom Color / Hex Code...")
        if self.config.target_color in ("blue", "green", "red", "orange"):
            self.combo_color.set_active_id(self.config.target_color)
        else:
            self.combo_color.set_active_id("custom")
        self.combo_color.connect("changed", self._on_color_combo_changed)
        grid2.attach(self.combo_color, 1, 0, 1, 1)

        # Custom Hex Entry
        self.entry_custom_color = Gtk.Entry(text=self.config.target_color)
        self.entry_custom_color.set_placeholder_text("#007bff or color name")
        self.entry_custom_color.set_visible(self.combo_color.get_active_id() == "custom")
        self.entry_custom_color.connect("changed", self._on_config_control_changed)
        grid2.attach(self.entry_custom_color, 2, 0, 1, 1)

        # Color Enforcement Mode
        grid2.attach(Gtk.Label(label="Color Mode:", xalign=0.0), 0, 1, 1, 1)
        self.combo_color_mode = Gtk.ComboBoxText()
        self.combo_color_mode.append("prefer", "Prefer Color (Recommended: Pick blue button if present, or any)")
        self.combo_color_mode.append("require", "Require Color (Strict: Only click if button matches color/style)")
        self.combo_color_mode.append("any", "Disabled (Match target text regardless of color)")
        self.combo_color_mode.set_active_id(self.config.color_mode)
        self.combo_color_mode.connect("changed", self._on_config_control_changed)
        grid2.attach(self.combo_color_mode, 1, 1, 2, 1)

        # Style & Class Keywords
        grid2.attach(Gtk.Label(label="Style Keywords:", xalign=0.0), 0, 2, 1, 1)
        self.entry_keywords = Gtk.Entry(text=", ".join(self.config.style_keywords))
        self.entry_keywords.set_tooltip_text("CSS classes or style indicators (e.g. suggested-action, primary, btn-primary)")
        self.entry_keywords.connect("changed", self._on_config_control_changed)
        grid2.attach(self.entry_keywords, 1, 2, 2, 1)

        # Allowed Roles
        grid2.attach(Gtk.Label(label="Allowed Roles:", xalign=0.0), 0, 3, 1, 1)
        self.entry_roles = Gtk.Entry(text=", ".join(self.config.allowed_roles))
        self.entry_roles.set_tooltip_text("Accessibility widget roles to scan (e.g. push button, button, link)")
        self.entry_roles.connect("changed", self._on_config_control_changed)
        grid2.attach(self.entry_roles, 1, 3, 2, 1)

        color_card.pack_start(grid2, False, False, 0)
        vbox.pack_start(color_card, False, False, 0)

        # 3. Action, Timing & Safety
        action_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        action_card.get_style_context().add_class("card")
        g3_title = Gtk.Label(label="3. CLICK ACTION & TIMING CONTROLS")
        g3_title.get_style_context().add_class("card-title")
        g3_title.set_xalign(0.0)
        action_card.pack_start(g3_title, False, False, 0)

        grid3 = Gtk.Grid(column_spacing=12, row_spacing=8)

        # Click method
        grid3.attach(Gtk.Label(label="Click Method:", xalign=0.0), 0, 0, 1, 1)
        self.combo_click_method = Gtk.ComboBoxText()
        self.combo_click_method.append("both", "Both (Native AT-SPI Action + Mouse Event - Best Compatibility)")
        self.combo_click_method.append("action", "Native AT-SPI Action Only (Fast, background)")
        self.combo_click_method.append("mouse", "Simulated Cursor Mouse Event Only")
        self.combo_click_method.set_active_id(self.config.click_method)
        self.combo_click_method.connect("changed", self._on_config_control_changed)
        grid3.attach(self.combo_click_method, 1, 0, 2, 1)

        # Polling interval
        grid3.attach(Gtk.Label(label="Polling Interval (s):", xalign=0.0), 0, 1, 1, 1)
        self.spin_poll = Gtk.SpinButton.new_with_range(0.1, 5.0, 0.1)
        self.spin_poll.set_value(self.config.poll_interval_sec)
        self.spin_poll.connect("value-changed", self._on_config_control_changed)
        grid3.attach(self.spin_poll, 1, 1, 1, 1)

        # Cooldown
        grid3.attach(Gtk.Label(label="Cooldown (s):", xalign=0.0), 0, 2, 1, 1)
        self.spin_cooldown = Gtk.SpinButton.new_with_range(0.5, 30.0, 0.5)
        self.spin_cooldown.set_value(self.config.cooldown_sec)
        self.spin_cooldown.connect("value-changed", self._on_config_control_changed)
        grid3.attach(self.spin_cooldown, 1, 2, 1, 1)

        # Max clicks per window
        grid3.attach(Gtk.Label(label="Max Clicks/Window:", xalign=0.0), 0, 3, 1, 1)
        self.spin_max_clicks = Gtk.SpinButton.new_with_range(0, 10, 1)
        self.spin_max_clicks.set_value(self.config.max_clicks_per_window)
        self.spin_max_clicks.connect("value-changed", self._on_config_control_changed)
        grid3.attach(self.spin_max_clicks, 1, 3, 1, 1)

        # Dry run / simulation
        grid3.attach(Gtk.Label(label="Simulation Mode (Dry Run):", xalign=0.0), 0, 4, 1, 1)
        self.switch_dry_run = Gtk.Switch(active=self.config.dry_run)
        self.switch_dry_run.set_tooltip_text("Detect and log buttons without actually clicking them")
        self.switch_dry_run.connect("notify::active", self._on_config_control_changed)
        grid3.attach(self.switch_dry_run, 1, 4, 1, 1)

        # Desktop notifications
        grid3.attach(Gtk.Label(label="Desktop Notifications:", xalign=0.0), 0, 5, 1, 1)
        self.switch_notify = Gtk.Switch(active=self.config.desktop_notifications)
        self.switch_notify.connect("notify::active", self._on_config_control_changed)
        grid3.attach(self.switch_notify, 1, 5, 1, 1)

        # Tab / Window title substring
        grid3.attach(Gtk.Label(label="Tab / Window Substring:", xalign=0.0), 0, 6, 1, 1)
        self.entry_tab_title_sub = Gtk.Entry(text=self.config.tab_title_substring)
        self.entry_tab_title_sub.set_placeholder_text("e.g. Permissions, Chrome, OAuth (clicks even when window loses focus)")
        self.entry_tab_title_sub.set_tooltip_text("When set, matches windows/tabs with this title substring even in the background!")
        self.entry_tab_title_sub.connect("changed", self._on_config_control_changed)
        grid3.attach(self.entry_tab_title_sub, 1, 6, 2, 1)

        # Require Window Focus
        grid3.attach(Gtk.Label(label="Require Window Focus:", xalign=0.0), 0, 7, 1, 1)
        self.switch_require_focus = Gtk.Switch(active=self.config.require_focus)
        self.switch_require_focus.set_tooltip_text("OFF = continues clicking target button even when window loses focus. ON = active focus only.")
        self.switch_require_focus.connect("notify::active", self._on_config_control_changed)
        grid3.attach(self.switch_require_focus, 1, 7, 1, 1)

        # Auto-raise window
        grid3.attach(Gtk.Label(label="Auto-Raise Window:", xalign=0.0), 0, 8, 1, 1)
        self.switch_auto_raise = Gtk.Switch(active=self.config.auto_raise_window)
        self.switch_auto_raise.set_tooltip_text("Bring target window to front before clicking if simulated mouse click is required.")
        self.switch_auto_raise.connect("notify::active", self._on_config_control_changed)
        grid3.attach(self.switch_auto_raise, 1, 8, 1, 1)

        action_card.pack_start(grid3, False, False, 0)
        vbox.pack_start(action_card, False, False, 0)

        # Save / Reset buttons
        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_bar.set_halign(Gtk.Align.END)

        reset_btn = Gtk.Button(label="Reset Defaults")
        reset_btn.connect("clicked", self._on_reset_defaults)

        save_btn = Gtk.Button(label="Save Configuration")
        save_btn.get_style_context().add_class("suggested-action")
        save_btn.connect("clicked", self._on_save_config)

        btn_bar.pack_start(reset_btn, False, False, 0)
        btn_bar.pack_start(save_btn, False, False, 0)
        vbox.pack_start(btn_bar, False, False, 0)

        scrolled.add(vbox)
        return scrolled

    def _connect_watcher_signals(self) -> None:
        """Connect callbacks from watcher engine to update UI on GLib thread."""
        self.watcher.on_status_changed = lambda is_on, msg: GLib.idle_add(self._ui_on_status_changed, is_on, msg)
        self.watcher.on_window_changed = lambda app, title: GLib.idle_add(self._ui_on_window_changed, app, title)
        self.watcher.on_button_detected = lambda match, app, title: GLib.idle_add(self._ui_on_button_detected, match, app, title)
        self.watcher.on_button_clicked = lambda match, app, title, succ, m: GLib.idle_add(self._ui_on_button_clicked, match, app, title, succ, m)
        self.watcher.on_log = lambda line, lvl: GLib.idle_add(self._ui_on_log, line, lvl)

    def _ui_on_status_changed(self, is_running: bool, message: str) -> None:
        if is_running:
            self.status_badge.set_text("ACTIVE - Watching")
            self.status_badge.get_style_context().remove_class("status-badge-stopped")
            self.status_badge.get_style_context().add_class("status-badge-active")
            self.toggle_watch_btn.set_label("Stop Watcher")
            self.toggle_watch_btn.get_style_context().remove_class("start-btn")
            self.toggle_watch_btn.get_style_context().add_class("stop-btn")
        else:
            self.status_badge.set_text("PAUSED")
            self.status_badge.get_style_context().remove_class("status-badge-active")
            self.status_badge.get_style_context().add_class("status-badge-stopped")
            self.toggle_watch_btn.set_label("Start Watcher")
            self.toggle_watch_btn.get_style_context().remove_class("stop-btn")
            self.toggle_watch_btn.get_style_context().add_class("start-btn")

    def _ui_on_window_changed(self, app_name: str, window_title: str) -> None:
        self.stat_windows_monitored += 1
        self.lbl_app_name.set_text(app_name or "Unknown Application")
        self.lbl_win_title.set_text(window_title or "(Untitled Window)")
        self._update_stats_label()

    def _ui_on_button_detected(self, match: MatchResult, app_name: str, window_title: str) -> None:
        self.stat_buttons_detected += 1
        self._update_stats_label()

    def _ui_on_button_clicked(
        self, match: MatchResult, app_name: str, window_title: str, success: bool, method: str
    ) -> None:
        if success:
            self.stat_clicks_executed += 1
            self._update_stats_label()

    def _ui_on_log(self, formatted_line: str, level: str) -> None:
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, formatted_line + "\n")
        # Auto scroll to bottom
        adj = self.log_view.get_vadjustment()
        if adj:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def _update_stats_label(self) -> None:
        self.lbl_stats.set_text(
            f"Windows: {self.stat_windows_monitored} | "
            f"Buttons Found: {self.stat_buttons_detected} | "
            f"Clicks Executed: {self.stat_clicks_executed}"
        )

    def _on_toggle_watcher(self, button: Gtk.Button) -> None:
        if self.watcher.is_running:
            self.watcher.stop()
        else:
            self._apply_current_ui_config()
            self.watcher.start(use_glib_timer=True)

    def _on_start_clicked(self, data: None) -> bool:
        if not self.watcher.is_running:
            self._apply_current_ui_config()
            self.watcher.start(use_glib_timer=True)
        return False

    def _on_launch_test_dialog(self, button: Gtk.Button) -> None:
        """Launch the test dialog popup."""
        if IS_MACOS:
            # GTK widgets are invisible to the macOS Accessibility API; use a native alert.
            from whacamole.backends.macos import open_native_test_dialog
            open_native_test_dialog(wait=False)
            return
        self._test_dialog = TestDialog()
        self._test_dialog.show_all()
        self._test_dialog.present()

    def _on_clear_log(self, button: Gtk.Button) -> None:
        self.log_buffer.set_text("")

    def _on_quick_tab_changed(self, entry: Gtk.Entry) -> None:
        val = entry.get_text().strip()
        self.config.tab_title_substring = val
        self.config.window_title_filter = val
        if hasattr(self, "entry_tab_title_sub") and self.entry_tab_title_sub.get_text() != val:
            self.entry_tab_title_sub.set_text(val)
        self.watcher.update_config(self.config)
        self._update_preview_badge()

    def _on_quick_focus_changed(self, switch: Gtk.Switch, *args) -> None:
        val = switch.get_active()
        self.config.require_focus = val
        if hasattr(self, "switch_require_focus") and self.switch_require_focus.get_active() != val:
            self.switch_require_focus.set_active(val)
        self.watcher.update_config(self.config)
        self._update_preview_badge()

    def _on_color_combo_changed(self, combo: Gtk.ComboBoxText) -> None:
        active_id = combo.get_active_id()
        is_custom = active_id == "custom"
        self.entry_custom_color.set_visible(is_custom)
        self._on_config_control_changed(combo)

    def _on_config_control_changed(self, widget: Gtk.Widget, *args) -> None:
        self._apply_current_ui_config()
        self._update_preview_badge()

    def _apply_current_ui_config(self) -> None:
        """Gather values from UI controls and update config."""
        self.config.target_text = self.entry_target_text.get_text().strip()
        self.config.text_match_mode = self.combo_match_mode.get_active_id() or "contains"
        self.config.case_sensitive = self.switch_case.get_active()

        color_id = self.combo_color.get_active_id()
        if color_id == "custom":
            self.config.target_color = self.entry_custom_color.get_text().strip() or "blue"
        else:
            self.config.target_color = color_id or "blue"

        self.config.color_mode = self.combo_color_mode.get_active_id() or "prefer"

        kws = [k.strip() for k in self.entry_keywords.get_text().split(",") if k.strip()]
        if kws:
            self.config.style_keywords = kws

        roles = [r.strip() for r in self.entry_roles.get_text().split(",") if r.strip()]
        if roles:
            self.config.allowed_roles = roles

        self.config.click_method = self.combo_click_method.get_active_id() or "both"
        self.config.poll_interval_sec = round(self.spin_poll.get_value(), 2)
        self.config.cooldown_sec = round(self.spin_cooldown.get_value(), 2)
        self.config.max_clicks_per_window = int(self.spin_max_clicks.get_value())
        self.config.dry_run = self.switch_dry_run.get_active()
        self.config.desktop_notifications = self.switch_notify.get_active()

        if hasattr(self, "entry_tab_title_sub"):
            sub = self.entry_tab_title_sub.get_text().strip()
            self.config.tab_title_substring = sub
            self.config.window_title_filter = sub
            if hasattr(self, "entry_quick_tab") and self.entry_quick_tab.get_text() != sub:
                self.entry_quick_tab.set_text(sub)

        if hasattr(self, "switch_require_focus"):
            req_f = self.switch_require_focus.get_active()
            self.config.require_focus = req_f
            if hasattr(self, "switch_quick_focus") and self.switch_quick_focus.get_active() != req_f:
                self.switch_quick_focus.set_active(req_f)

        if hasattr(self, "switch_auto_raise"):
            self.config.auto_raise_window = self.switch_auto_raise.get_active()

        # Update watcher
        self.watcher.update_config(self.config)

    def _update_preview_badge(self) -> None:
        """Dynamically style the preview badge according to selected color/style."""
        self.preview_btn.set_label(self.config.target_text or "Allow")

        color = self.config.target_color.lower().strip()
        bg_color = "#007bff"
        fg_color = "#ffffff"

        if color == "blue" or "#007bff" in color or "#0d6efd" in color:
            bg_color = "#0d6efd"
        elif color == "green":
            bg_color = "#198754"
        elif color == "red":
            bg_color = "#dc3545"
        elif color == "orange":
            bg_color = "#fd7e14"
        elif color.startswith("#") or color.startswith("rgb"):
            bg_color = color

        css = f"""
        button.target-preview-btn {{
            background-color: {bg_color};
            color: {fg_color};
        }}
        """.encode("utf-8")

        provider = Gtk.CssProvider()
        try:
            provider.load_from_data(css)
            ctx = self.preview_btn.get_style_context()
            ctx.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:
            pass

        focus_info = "Focus: Active Only" if self.config.require_focus else "Focus: Background & Active"
        tab_info = f" | Tab: '{self.config.tab_title_substring}'" if self.config.tab_title_substring else " | Tab: Any"
        self.lbl_target_info.set_text(
            f"Color: {self.config.target_color.capitalize()}\n"
            f"Mode: {self.config.color_mode.capitalize()} | Click: {self.config.click_method}\n"
            f"{focus_info}{tab_info}"
        )

    def _on_save_config(self, button: Gtk.Button) -> None:
        self._apply_current_ui_config()
        path = self.config.save_to_file()
        self._ui_on_log(f"[{time.strftime('%H:%M:%S')}] [INFO] Configuration saved to {path}", "INFO")

    def _on_reset_defaults(self, button: Gtk.Button) -> None:
        self.config = WatcherConfig()
        # Reset UI
        self.entry_target_text.set_text(self.config.target_text)
        self.combo_match_mode.set_active_id(self.config.text_match_mode)
        self.switch_case.set_active(self.config.case_sensitive)
        self.combo_color.set_active_id(self.config.target_color)
        self.combo_color_mode.set_active_id(self.config.color_mode)
        self.entry_keywords.set_text(", ".join(self.config.style_keywords))
        self.entry_roles.set_text(", ".join(self.config.allowed_roles))
        self.combo_click_method.set_active_id(self.config.click_method)
        self.spin_poll.set_value(self.config.poll_interval_sec)
        self.spin_cooldown.set_value(self.config.cooldown_sec)
        self.spin_max_clicks.set_value(self.config.max_clicks_per_window)
        self.switch_dry_run.set_active(self.config.dry_run)
        self.switch_notify.set_active(self.config.desktop_notifications)
        if hasattr(self, "entry_tab_title_sub"):
            self.entry_tab_title_sub.set_text("")
        if hasattr(self, "entry_quick_tab"):
            self.entry_quick_tab.set_text("")
        if hasattr(self, "switch_require_focus"):
            self.switch_require_focus.set_active(False)
        if hasattr(self, "switch_quick_focus"):
            self.switch_quick_focus.set_active(False)
        if hasattr(self, "switch_auto_raise"):
            self.switch_auto_raise.set_active(False)
        self._apply_current_ui_config()
        self._update_preview_badge()
        self._ui_on_log(f"[{time.strftime('%H:%M:%S')}] [INFO] Reset configuration to default values", "INFO")


def launch_gui(config: Optional[WatcherConfig] = None) -> None:
    """Launch the Whac-A-Mole GTK GUI application."""
    display = Gdk.Display.get_default()
    if not display or not Gtk.init_check()[0]:
        raise RuntimeError("No graphical display available (cannot connect to a display server)")

    win = WhacamoleWindow(config)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    launch_gui()
