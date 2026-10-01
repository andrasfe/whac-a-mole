"""Configuration management for Whac-A-Mole button watcher."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "whacamole"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


@dataclass
class WatcherConfig:
    """Configuration settings for button detection and automated clicking."""

    # Target text to match on buttons
    target_text: str = "Allow"

    # Matching mode for text: 'contains', 'exact', 'regex'
    text_match_mode: str = "contains"

    # Whether text matching is case sensitive
    case_sensitive: bool = False

    # Target color name (e.g. 'blue', 'green', 'red') or hex (e.g. '#007bff')
    target_color: str = "blue"

    # Color filtering enforcement:
    # 'prefer': prioritize matching blue/primary buttons over other buttons
    # 'require': only click if the button matches the color/style criteria
    # 'any': match target text regardless of color/style
    color_mode: str = "prefer"

    # Style/class keywords indicating primary / target styling
    style_keywords: List[str] = field(
        default_factory=lambda: [
            "suggested-action",
            "primary",
            "btn-primary",
            "btn-blue",
            "blue",
            "accent",
            "action-blue",
            "confirm",
            "unelevated",
            "mat-mdc-unelevated-button",
            "mdc-button--unelevated",
            "filled",
            "mat-primary",
        ]
    )

    # Allowed accessible widget roles
    allowed_roles: List[str] = field(
        default_factory=lambda: [
            "push button",
            "button",
            "link",
            "toggle button",
            "menu item",
        ]
    )

    # Polling frequency in seconds
    poll_interval_sec: float = 0.5

    # Delay before clicking once button is found (seconds)
    click_delay_sec: float = 0.1

    # Cooldown period per window / button to avoid rapid double-clicking (seconds)
    cooldown_sec: float = 2.0

    # How to perform the click: 'action' (native AT-SPI action), 'mouse' (synthesized cursor click), 'both'
    click_method: str = "both"

    # Substrings or regex for windows to exclude (e.g., self, system desktop components)
    exclude_windows: List[str] = field(
        default_factory=lambda: [
            "Whac-A-Mole",
            "whacamole",
            "gnome-shell",
            "desktop-icons",
            "mutter",
            "gjs",
        ]
    )

    # Substring of window title or browser tab title to watch (e.g. 'Permissions', 'Meet', 'OAuth')
    tab_title_substring: str = ""

    # Backward-compatible alias for tab_title_substring
    window_title_filter: str = ""

    # Whether the window must have active input focus to be clicked.
    # Set to False (default) so buttons in background windows/tabs are clicked even when focus is lost!
    require_focus: bool = False

    # Whether to automatically raise / bring the window to the front if simulated mouse click is used
    auto_raise_window: bool = False

    # Maximum tree depth when scanning window accessibility hierarchy (60+ reaches deep web/Electron DOMs)
    max_traversal_depth: int = 60

    # Maximum clicks allowed on a single window instance (0 for unlimited, debounced by cooldown)
    max_clicks_per_window: int = 0

    # Simulation mode: log detection without clicking
    dry_run: bool = False

    # Show desktop notification on click
    desktop_notifications: bool = True

    # Play sound alert on click
    sound_alert: bool = True

    # Automatically start watching when app starts
    auto_start: bool = True

    def __post_init__(self) -> None:
        """Sync tab_title_substring and window_title_filter."""
        if self.tab_title_substring and not self.window_title_filter:
            self.window_title_filter = self.tab_title_substring
        elif self.window_title_filter and not self.tab_title_substring:
            self.tab_title_substring = self.window_title_filter

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WatcherConfig:
        """Create config from dictionary, ignoring unknown keys."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        cfg = cls(**filtered)
        if cfg.tab_title_substring and not cfg.window_title_filter:
            cfg.window_title_filter = cfg.tab_title_substring
        elif cfg.window_title_filter and not cfg.tab_title_substring:
            cfg.tab_title_substring = cfg.window_title_filter
        return cfg

    def save_to_file(self, path: Path | str | None = None) -> Path:
        """Save configuration to a JSON file."""
        target_path = Path(path) if path else DEFAULT_CONFIG_FILE
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return target_path

    @classmethod
    def load_from_file(cls, path: Path | str | None = None) -> WatcherConfig:
        """Load configuration from a JSON file, or return defaults if not found."""
        target_path = Path(path) if path else DEFAULT_CONFIG_FILE
        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls.from_dict(data)
            except Exception as e:
                print(f"[Whac-A-Mole] Warning: Failed to load config from {target_path} ({e}), using defaults.")
        return cls()
