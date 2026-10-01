"""Live integration test: window watcher detecting and auto-clicking a real GTK dialog."""

import time
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Atspi", "2.0")
from gi.repository import Gtk, Atspi

from whacamole.config import WatcherConfig
from whacamole.test_dialog import TestDialog
from whacamole.watcher import WindowWatcher


def test_live_gtk_dialog_auto_click():
    # Setup test dialog
    dialog = TestDialog(title="Integration Test Dialog Window")
    dialog.show_all()

    # Pump GTK events so window is mapped and accessible in AT-SPI
    for _ in range(15):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.02)

    initial_clicks = dialog.click_count
    assert initial_clicks == 0

    # Configure watcher
    cfg = WatcherConfig(
        target_text="Allow",
        target_color="blue",
        color_mode="prefer",
        click_delay_sec=0.0,
        cooldown_sec=1.0,
        desktop_notifications=False,
        sound_alert=False,
        click_method="action",
        exclude_windows=[],  # Don't exclude for test
    )
    watcher = WindowWatcher(cfg)

    # Find the dialog accessible object
    desktop = Atspi.get_desktop(0)
    dialog_acc = None
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if not app:
            continue
        for j in range(app.get_child_count()):
            w = app.get_child_at_index(j)
            if w and "Integration Test Dialog Window" in (w.get_name() or ""):
                dialog_acc = w
                break
        if dialog_acc:
            break

    assert dialog_acc is not None, "Failed to find Integration Test Dialog in AT-SPI tree"

    # Scan and find buttons in this dialog
    matches = watcher.scan_window_buttons(dialog_acc)
    assert len(matches) >= 1, "Expected at least one matching button"

    best_match = matches[0]
    assert best_match.text == "Allow"
    assert "suggested-action" in best_match.style_matches or "blue" in best_match.style_matches

    # Execute click via watcher logic
    win_key = "TestApp::Integration Test Dialog Window"
    from whacamole.watcher import WindowInfo
    win_info = WindowInfo("TestApp", "Integration Test Dialog Window", dialog_acc, True)

    watcher._execute_click(best_match, win_info, win_key)

    # Pump GTK event loop to process click signal
    for _ in range(15):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.02)

    # Verify button received click
    assert dialog.click_count == 1, f"Expected 1 click, got {dialog.click_count}"

    # Cleanup
    dialog.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def test_live_dialog_clicks_when_focus_lost_by_tab_title():
    """Live test: target dialog LOSES focus to another window, but is still clicked via tab_title_substring."""
    dialog = TestDialog(title="OAuth Permission Request - Google Chrome")
    dialog.show_all()

    # Another window that steals focus
    other_win = Gtk.Window(title="Foreground Work Terminal")
    other_win.show_all()
    other_win.present()

    for _ in range(15):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.02)

    initial_clicks = dialog.click_count
    assert initial_clicks == 0

    cfg = WatcherConfig(
        target_text="Allow",
        tab_title_substring="Permission",
        require_focus=False,  # Can click even when focus lost!
        click_delay_sec=0.0,
        cooldown_sec=1.0,
        desktop_notifications=False,
        sound_alert=False,
        click_method="action",
        exclude_windows=[],
    )
    watcher = WindowWatcher(cfg)

    # Run scan_and_act: should find the unfocused dialog by tab title and click Allow!
    watcher.scan_and_act()

    for _ in range(15):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.02)

    assert dialog.click_count == 1, f"Expected 1 click in background, got {dialog.click_count}"

    dialog.destroy()
    other_win.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
