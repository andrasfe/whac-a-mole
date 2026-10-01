"""Command Line Interface for Whac-A-Mole."""

from __future__ import annotations

import argparse
import signal
import sys
import time

from whacamole import __version__
from whacamole.backends import IS_MACOS
from whacamole.config import WatcherConfig
from whacamole.watcher import WindowWatcher


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="whacamole",
        description="Active-window button watcher and auto-clicker for blue Allow buttons (configurable).",
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--headless", "--no-gui",
        action="store_true",
        help="Run in headless CLI mode without opening the GTK user interface.",
    )

    parser.add_argument(
        "--test-dialog",
        action="store_true",
        help="Launch the interactive demo dialog with a blue Allow button to test detection (native alert on macOS).",
    )

    parser.add_argument(
        "-t", "--text",
        dest="target_text",
        help="Target button text to match (e.g., 'Allow', 'Agree', 'Accept').",
    )

    parser.add_argument(
        "-c", "--color",
        dest="target_color",
        help="Target button color name or hex code (e.g., 'blue', 'green', '#007bff').",
    )

    parser.add_argument(
        "--color-mode",
        choices=["prefer", "require", "any"],
        help="Color matching requirement: 'prefer' (prioritize matching color), 'require' (strict), 'any' (ignore color).",
    )

    parser.add_argument(
        "--match-mode",
        choices=["contains", "exact", "regex"],
        dest="text_match_mode",
        help="Text matching mode.",
    )

    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        default=None,
        help="Enable case-sensitive text matching.",
    )

    parser.add_argument(
        "--click-method",
        choices=["both", "action", "mouse"],
        help="Method used to trigger click: 'action' (native accessibility action: AT-SPI / macOS AXPress), 'mouse' (synthesized cursor click), 'both'.",
    )

    parser.add_argument(
        "--poll-interval",
        type=float,
        dest="poll_interval_sec",
        help="Interval between window checks in seconds (e.g. 0.5).",
    )

    parser.add_argument(
        "--cooldown",
        type=float,
        dest="cooldown_sec",
        help="Cooldown in seconds between clicks on the same window.",
    )

    parser.add_argument(
        "-s", "--tab-title", "--window-title", "--title-substring", "--title",
        dest="tab_title_substring",
        help="Substring of window or browser tab title to watch (clicks button even when window loses focus!).",
    )

    parser.add_argument(
        "--require-focus",
        dest="require_focus",
        action="store_true",
        default=None,
        help="Strictly require the target window to have active input focus.",
    )

    parser.add_argument(
        "--no-require-focus",
        dest="require_focus",
        action="store_false",
        help="Allow watching and clicking target buttons in background windows/tabs when focus is lost.",
    )

    parser.add_argument(
        "--auto-raise",
        dest="auto_raise_window",
        action="store_true",
        default=None,
        help="Automatically raise/focus the target window before clicking.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Simulation mode: detect buttons and log actions without executing clicks.",
    )

    parser.add_argument(
        "--config",
        dest="config_path",
        help="Path to custom JSON configuration file.",
    )

    parser.add_argument(
        "--save-default-config",
        action="store_true",
        help="Write default configuration to config file and exit.",
    )

    return parser.parse_args(argv)


def run_headless(config: WatcherConfig) -> None:
    """Run watcher in headless terminal mode."""
    print("=" * 65)
    print(f"  Whac-A-Mole Button Watcher v{__version__} [HEADLESS MODE]")
    print("=" * 65)
    print(f"  Target Text:    '{config.target_text}' (mode: {config.text_match_mode})")
    print(f"  Target Color:   '{config.target_color}' (mode: {config.color_mode})")
    print(f"  Tab/Win Title:  '{config.tab_title_substring or '(Any)'}' (require_focus={config.require_focus})")
    print(f"  Click Method:   {config.click_method}")
    print(f"  Poll Interval:  {config.poll_interval_sec}s")
    print(f"  Cooldown:       {config.cooldown_sec}s")
    print(f"  Dry Run:        {config.dry_run}")
    print("=" * 65)
    print("Press Ctrl+C to stop watching...\n")

    watcher = WindowWatcher(config)

    def handle_signal(sig, frame):
        print("\n[Whac-A-Mole] Stopping watcher...")
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    watcher.start(use_glib_timer=False)

    try:
        while watcher.is_running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        watcher.stop()


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    args = parse_args(argv)

    if args.save_default_config:
        cfg = WatcherConfig()
        saved = cfg.save_to_file(args.config_path)
        print(f"[Whac-A-Mole] Default configuration written to {saved}")
        sys.exit(0)

    if args.test_dialog:
        print("[Whac-A-Mole] Launching interactive test dialog...")
        if IS_MACOS:
            from whacamole.backends.macos import open_native_test_dialog
            clicked = open_native_test_dialog(wait=True)
            print(f"[Whac-A-Mole] Test dialog closed (button: {clicked or 'none'})")
        else:
            from whacamole.test_dialog import launch_test_dialog
            launch_test_dialog()
        sys.exit(0)

    # Load configuration
    config = WatcherConfig.load_from_file(args.config_path)

    # Override config with any provided CLI flags
    if args.target_text is not None:
        config.target_text = args.target_text
    if args.target_color is not None:
        config.target_color = args.target_color
    if args.color_mode is not None:
        config.color_mode = args.color_mode
    if args.text_match_mode is not None:
        config.text_match_mode = args.text_match_mode
    if args.case_sensitive is not None:
        config.case_sensitive = args.case_sensitive
    if args.click_method is not None:
        config.click_method = args.click_method
    if args.poll_interval_sec is not None:
        config.poll_interval_sec = args.poll_interval_sec
    if args.cooldown_sec is not None:
        config.cooldown_sec = args.cooldown_sec
    if args.dry_run is not None:
        config.dry_run = args.dry_run
    if args.tab_title_substring is not None:
        config.tab_title_substring = args.tab_title_substring
        config.window_title_filter = args.tab_title_substring
    if args.require_focus is not None:
        config.require_focus = args.require_focus
    if args.auto_raise_window is not None:
        config.auto_raise_window = args.auto_raise_window

    if args.headless:
        run_headless(config)
    else:
        try:
            from whacamole.gui import launch_gui
            launch_gui(config)
        except Exception as e:
            print(f"[Whac-A-Mole] Notice: GTK GUI could not be initialized ({e}).")
            print("[Whac-A-Mole] Falling back to headless mode...")
            run_headless(config)


if __name__ == "__main__":
    main()
