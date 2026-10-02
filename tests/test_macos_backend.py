"""Unit tests for the macOS accessibility backend adapters."""

import sys

import pytest

if sys.platform != "darwin":
    pytest.skip("macOS backend requires PyObjC on macOS", allow_module_level=True)

from whacamole.backends import macos
from whacamole.backends.macos import MacElement, ax_role_to_role_name
from whacamole.config import WatcherConfig
from whacamole.matcher import ButtonMatcher


def test_role_mapping():
    assert ax_role_to_role_name("AXButton") == "push button"
    assert ax_role_to_role_name("AXLink") == "link"
    assert ax_role_to_role_name("AXCheckBox", "AXToggle") == "toggle button"
    assert ax_role_to_role_name("AXRadioButton", "AXTabButton") == "page tab"
    assert ax_role_to_role_name("AXPopUpButton") == "combo box"
    assert ax_role_to_role_name("AXDisclosureTriangle") == "disclosure triangle"


def _fake_element(monkeypatch, attrs, actions=("AXPress",)):
    def fake_get(ref, attribute):
        return attrs.get(attribute)

    monkeypatch.setattr(macos, "_ax_get", fake_get)
    monkeypatch.setattr(macos, "_ax_value", lambda value, value_type: value)
    elem = MacElement(object())
    monkeypatch.setattr(elem, "_action_names", lambda: list(actions))
    return elem


class _Point:
    def __init__(self, x, y):
        self.x, self.y = x, y


class _Size:
    def __init__(self, w, h):
        self.width, self.height = w, h


def test_mac_element_matches_web_primary_button(monkeypatch):
    elem = _fake_element(monkeypatch, {
        "AXRole": "AXButton",
        "AXTitle": "",
        "AXDescription": "Allow",
        "AXEnabled": True,
        "AXDOMClassList": ["mdc-button", "mat-primary"],
        "AXPosition": _Point(300, 400),
        "AXSize": _Size(80, 32),
    })
    result = ButtonMatcher(WatcherConfig(target_text="Allow")).evaluate(elem)
    assert result.matched
    assert result.role == "push button"
    assert result.center == (340, 416)
    assert "mat-primary" in result.style_matches


def test_mac_element_hidden_is_rejected(monkeypatch):
    elem = _fake_element(monkeypatch, {
        "AXRole": "AXButton",
        "AXTitle": "Allow",
        "AXHidden": True,
        "AXPosition": _Point(10, 10),
        "AXSize": _Size(80, 32),
    })
    assert not ButtonMatcher(WatcherConfig()).evaluate(elem).matched


def test_mac_element_window_states(monkeypatch):
    elem = _fake_element(monkeypatch, {"AXRole": "AXWindow", "AXMain": True})
    elem.app_pid = elem.frontmost_pid = 42
    states = {s.value_nick for s in elem.get_state_set().get_states()}
    assert {"showing", "visible", "active"} <= states


def test_mac_element_do_action_prefers_press(monkeypatch):
    elem = _fake_element(monkeypatch, {}, actions=("AXShowMenu", "AXPress"))
    performed = []
    monkeypatch.setattr(macos.AX, "AXUIElementPerformAction", lambda ref, a: performed.append(a) or 0)
    assert elem.do_action(0) is True
    assert performed == ["AXPress"]


def test_mac_element_disabled_is_rejected(monkeypatch):
    """Stale, disabled 'Allow' buttons left in a web chat history must not match."""
    elem = _fake_element(monkeypatch, {
        "AXRole": "AXButton",
        "AXTitle": "Allow",
        "AXEnabled": False,
        "AXPosition": _Point(10, 10),
        "AXSize": _Size(80, 32),
    })
    result = ButtonMatcher(WatcherConfig()).evaluate(elem)
    assert not result.matched
    assert result.reasons == ["Element is disabled"]
