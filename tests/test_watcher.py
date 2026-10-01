"""Unit tests for window watcher."""

import time
from unittest.mock import MagicMock
from whacamole.config import WatcherConfig
from whacamole.matcher import MatchResult
from whacamole.watcher import WindowInfo, WindowWatcher
from tests.test_matcher import make_mock_element


def test_watcher_scan_and_click():
    cfg = WatcherConfig(
        target_text="Allow",
        click_delay_sec=0.0,
        cooldown_sec=1.0,
        desktop_notifications=False,
        sound_alert=False,
        click_method="action",
    )
    watcher = WindowWatcher(cfg)

    # Mock action call on element
    mock_btn = make_mock_element(name="Allow", role="push button")
    mock_btn.get_n_actions.return_value = 1
    mock_btn.do_action.return_value = True

    # Mock window
    mock_win = MagicMock()
    mock_win.get_name.return_value = "Permission Dialog"
    mock_win.get_child_count.return_value = 1
    mock_win.get_child_at_index.return_value = mock_btn

    win_info = WindowInfo(
        app_name="TestApp",
        window_title="Permission Dialog",
        accessible=mock_win,
        is_active=True,
    )

    watcher.get_target_windows = MagicMock(return_value=[win_info])

    clicked_events = []
    watcher.on_button_clicked = lambda match, app, title, succ, m: clicked_events.append((app, title, succ))

    # Run scan
    watcher.scan_and_act()

    # Verify click was invoked
    assert len(clicked_events) == 1
    assert clicked_events[0] == ("TestApp", "Permission Dialog", True)
    assert mock_btn.do_action.called


def test_watcher_cooldown():
    cfg = WatcherConfig(
        target_text="Allow",
        click_delay_sec=0.0,
        cooldown_sec=10.0,
        desktop_notifications=False,
        sound_alert=False,
        max_clicks_per_window=1,
    )
    watcher = WindowWatcher(cfg)

    mock_btn = make_mock_element(name="Allow")
    mock_btn.get_n_actions.return_value = 1
    mock_btn.do_action.return_value = True

    mock_win = MagicMock()
    mock_win.get_child_count.return_value = 1
    mock_win.get_child_at_index.return_value = mock_btn

    win_info = WindowInfo(
        app_name="App",
        window_title="Prompt",
        accessible=mock_win,
        is_active=True,
    )
    watcher.get_target_windows = MagicMock(return_value=[win_info])

    clicked = []
    watcher.on_button_clicked = lambda *args: clicked.append(True)

    # First scan: should click
    watcher.scan_and_act()
    assert len(clicked) == 1

    # Second scan immediately: should be ignored due to cooldown / max_clicks
    watcher.scan_and_act()
    assert len(clicked) == 1


def test_watcher_background_tab_title_click():
    """Test that a window matching tab_title_substring is clicked even when it loses focus (is_active=False)."""
    cfg = WatcherConfig(
        target_text="Allow",
        tab_title_substring="Permissions",
        require_focus=False,  # Can click in background
        click_delay_sec=0.0,
        cooldown_sec=1.0,
        desktop_notifications=False,
        sound_alert=False,
        click_method="action",
    )
    watcher = WindowWatcher(cfg)

    mock_btn = make_mock_element(name="Allow", role="push button")
    mock_btn.get_n_actions.return_value = 1
    mock_btn.do_action.return_value = True

    mock_win = MagicMock()
    mock_win.get_name.return_value = "Site Permissions - Google Chrome"
    mock_win.get_child_count.return_value = 1
    mock_win.get_child_at_index.return_value = mock_btn

    # Window has LOST focus (is_active = False)
    unfocused_win = WindowInfo(
        app_name="Google Chrome",
        window_title="Site Permissions - Google Chrome",
        accessible=mock_win,
        is_active=False,
    )

    watcher.get_target_windows = MagicMock(return_value=[unfocused_win])

    clicked_events = []
    watcher.on_button_clicked = lambda match, app, title, succ, m: clicked_events.append((app, title, succ))

    watcher.scan_and_act()

    # Click should be executed despite being in background!
    assert len(clicked_events) == 1
    assert clicked_events[0] == ("Google Chrome", "Site Permissions - Google Chrome", True)
    assert mock_btn.do_action.called


def test_watcher_require_focus_rejection():
    """Test that when require_focus is True, unfocused background windows are skipped."""
    cfg = WatcherConfig(
        target_text="Allow",
        tab_title_substring="Permissions",
        require_focus=True,  # Strictly require focus
        click_delay_sec=0.0,
    )
    watcher = WindowWatcher(cfg)

    # Mock window in AT-SPI desktop that is NOT active
    mock_win = MagicMock()
    mock_win.get_name.return_value = "Site Permissions - Google Chrome"
    mock_win.get_state_set.return_value = MagicMock(
        get_states=lambda: [MagicMock(value_nick="showing"), MagicMock(value_nick="visible")]
    )  # No "active" state

    mock_app = MagicMock()
    mock_app.get_name.return_value = "Google Chrome"
    mock_app.get_child_count.return_value = 1
    mock_app.get_child_at_index.return_value = mock_win

    mock_desktop = MagicMock()
    mock_desktop.get_child_count.return_value = 1
    mock_desktop.get_child_at_index.return_value = mock_app

    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    Atspi.get_desktop = MagicMock(return_value=mock_desktop)

    # With require_focus=True, get_target_windows should return empty list
    targets = watcher.get_target_windows()
    assert len(targets) == 0
