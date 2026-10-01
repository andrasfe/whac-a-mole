"""Unit tests for button matcher module."""

from unittest.mock import MagicMock
from whacamole.config import WatcherConfig
from whacamole.matcher import ButtonMatcher


class MockState:
    def __init__(self, name):
        self.value_nick = name


class MockStateSet:
    def __init__(self, states):
        self._states = [MockState(s) for s in states]

    def get_states(self):
        return self._states


class MockRect:
    def __init__(self, x=100, y=200, width=80, height=35):
        self.x = x
        self.y = y
        self.width = width
        self.height = height


def make_mock_element(
    name="Allow",
    role="push button",
    attributes=None,
    states=None,
    description="",
    rect=None,
):
    elem = MagicMock()
    elem.get_name.return_value = name
    elem.get_role_name.return_value = role
    elem.get_description.return_value = description
    elem.get_attributes.return_value = attributes or {"toolkit": "gtk"}
    elem.get_state_set.return_value = MockStateSet(states or ["showing", "visible", "enabled"])
    elem.get_child_count.return_value = 0
    elem.get_extents.return_value = rect or MockRect()
    return elem


def test_text_matching_contains():
    cfg = WatcherConfig(target_text="Allow", text_match_mode="contains", case_sensitive=False)
    matcher = ButtonMatcher(cfg)

    elem1 = make_mock_element(name="Allow")
    res1 = matcher.evaluate(elem1)
    assert res1.matched is True

    elem2 = make_mock_element(name="Always Allow")
    res2 = matcher.evaluate(elem2)
    assert res2.matched is True

    # Opposing buttons must be rejected
    elem3 = make_mock_element(name="Don't Allow")
    assert matcher.evaluate(elem3).matched is False

    elem4 = make_mock_element(name="Disallow")
    assert matcher.evaluate(elem4).matched is False

    elem5 = make_mock_element(name="Cancel")
    assert matcher.evaluate(elem5).matched is False


def test_text_matching_exact():
    cfg = WatcherConfig(target_text="Agree", text_match_mode="exact", case_sensitive=False)
    matcher = ButtonMatcher(cfg)

    elem1 = make_mock_element(name="Agree")
    res1 = matcher.evaluate(elem1)
    assert res1.matched is True

    elem2 = make_mock_element(name="I Agree")
    res2 = matcher.evaluate(elem2)
    assert res2.matched is False


def test_text_matching_regex():
    cfg = WatcherConfig(target_text=r"^(I\s+)?Agree$", text_match_mode="regex")
    matcher = ButtonMatcher(cfg)

    elem1 = make_mock_element(name="Agree")
    assert matcher.evaluate(elem1).matched is True

    elem2 = make_mock_element(name="I Agree")
    assert matcher.evaluate(elem2).matched is True

    elem3 = make_mock_element(name="Do not agree")
    assert matcher.evaluate(elem3).matched is False


def test_role_filtering():
    cfg = WatcherConfig(allowed_roles=["push button", "button"])
    matcher = ButtonMatcher(cfg)

    elem_btn = make_mock_element(name="Allow", role="push button")
    assert matcher.evaluate(elem_btn).matched is True

    elem_heading = make_mock_element(name="Allow", role="heading")
    assert matcher.evaluate(elem_heading).matched is False


def test_color_mode_require():
    # Require blue/primary style
    cfg = WatcherConfig(
        target_text="Allow",
        target_color="blue",
        color_mode="require",
        style_keywords=["suggested-action", "primary", "blue"],
    )
    matcher = ButtonMatcher(cfg)

    # Element with blue style class
    blue_elem = make_mock_element(
        name="Allow",
        attributes={"class": "btn suggested-action", "toolkit": "gtk"},
    )
    res_blue = matcher.evaluate(blue_elem)
    assert res_blue.matched is True
    assert len(res_blue.style_matches) > 0

    # Element with gray / unstyled attributes
    plain_elem = make_mock_element(
        name="Allow",
        attributes={"class": "btn btn-secondary", "toolkit": "gtk"},
    )
    res_plain = matcher.evaluate(plain_elem)
    assert res_plain.matched is False
    assert "Color/style match required" in res_plain.reasons[0]


def test_color_mode_prefer():
    # Prefer blue button: both match, but blue button gets higher score
    cfg = WatcherConfig(
        target_text="Allow",
        target_color="blue",
        color_mode="prefer",
        style_keywords=["suggested-action", "primary", "blue"],
    )
    matcher = ButtonMatcher(cfg)

    blue_elem = make_mock_element(
        name="Allow",
        attributes={"class": "btn suggested-action"},
    )
    plain_elem = make_mock_element(
        name="Allow",
        attributes={"class": "btn"},
    )

    res_blue = matcher.evaluate(blue_elem)
    res_plain = matcher.evaluate(plain_elem)

    assert res_blue.matched is True
    assert res_plain.matched is True
    assert res_blue.score > res_plain.score


def test_web_element_states_accepted():
    # Chromium web elements often only have enabled/sensitive without explicit showing/visible
    cfg = WatcherConfig(target_text="Allow")
    matcher = ButtonMatcher(cfg)

    web_elem = make_mock_element(
        name="Allow",
        role="push button",
        states=["enabled", "sensitive", "focusable"],
        rect=MockRect(x=500, y=300, width=100, height=40),
    )
    res = matcher.evaluate(web_elem)
    assert res.matched is True


def test_offscreen_element_rejected():
    # Elements scrolled into negative coordinates (e.g. chat history) must be rejected
    cfg = WatcherConfig(target_text="Allow")
    matcher = ButtonMatcher(cfg)

    offscreen_elem = make_mock_element(
        name="Allow",
        role="push button",
        states=["enabled", "sensitive"],
        rect=MockRect(x=1900, y=-1996, width=72, height=49),
    )
    res = matcher.evaluate(offscreen_elem)
    assert res.matched is False
    assert "off-screen" in res.reasons[0]


def test_zero_dimension_element_rejected():
    # Zero width or height elements must be rejected
    cfg = WatcherConfig(target_text="Allow")
    matcher = ButtonMatcher(cfg)

    zero_elem = make_mock_element(
        name="Allow",
        role="push button",
        states=["enabled", "sensitive"],
        rect=MockRect(x=100, y=100, width=0, height=0),
    )
    res = matcher.evaluate(zero_elem)
    assert res.matched is False
    assert "zero-sized" in res.reasons[0]
