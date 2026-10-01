"""Unit tests for configuration module."""

import json
from pathlib import Path
from whacamole.config import WatcherConfig


def test_default_config():
    cfg = WatcherConfig()
    assert cfg.target_text == "Allow"
    assert cfg.target_color == "blue"
    assert cfg.color_mode == "prefer"
    assert cfg.text_match_mode == "contains"
    assert cfg.case_sensitive is False
    assert cfg.tab_title_substring == ""
    assert cfg.require_focus is False
    assert "suggested-action" in cfg.style_keywords
    assert cfg.poll_interval_sec == 0.5


def test_tab_title_config_sync():
    cfg1 = WatcherConfig(tab_title_substring="Google Chrome")
    assert cfg1.window_title_filter == "Google Chrome"

    cfg2 = WatcherConfig(window_title_filter="OAuth Dialog")
    assert cfg2.tab_title_substring == "OAuth Dialog"

    cfg3 = WatcherConfig.from_dict({"tab_title_substring": "Permissions", "require_focus": False})
    assert cfg3.tab_title_substring == "Permissions"
    assert cfg3.window_title_filter == "Permissions"
    assert cfg3.require_focus is False


def test_config_serialization(tmp_path: Path):
    cfg = WatcherConfig(
        target_text="Accept",
        target_color="green",
        color_mode="require",
        poll_interval_sec=1.0,
    )
    d = cfg.to_dict()
    assert d["target_text"] == "Accept"
    assert d["target_color"] == "green"
    assert d["color_mode"] == "require"

    file_path = tmp_path / "test_config.json"
    saved = cfg.save_to_file(file_path)
    assert saved.exists()

    loaded = WatcherConfig.load_from_file(file_path)
    assert loaded.target_text == "Accept"
    assert loaded.target_color == "green"
    assert loaded.color_mode == "require"
    assert loaded.poll_interval_sec == 1.0
