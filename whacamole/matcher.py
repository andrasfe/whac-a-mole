"""Button matching engine for Whac-A-Mole.

Evaluates accessibility elements against configurable rules for text,
role, style classes, and color indicators.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from whacamole.config import WatcherConfig


# Common color keyword mappings
COLOR_KEYWORDS: Dict[str, List[str]] = {
    "blue": [
        "blue",
        "azure",
        "navy",
        "cyan",
        "primary",
        "btn-primary",
        "btn-blue",
        "suggested-action",
        "accent",
        "#007bff",
        "#0d6efd",
        "#1e88e5",
        "#1976d2",
        "#2196f3",
        "#3584e4",
        "#1c71d8",
        "rgb(0, 123, 255)",
        "rgb(13, 110, 253)",
    ],
    "green": [
        "green",
        "success",
        "btn-success",
        "#28a745",
        "#198754",
        "#4caf50",
        "#2ec27e",
        "#26a269",
    ],
    "red": [
        "red",
        "danger",
        "destructive",
        "destructive-action",
        "btn-danger",
        "#dc3545",
        "#e01b24",
        "#f44336",
    ],
    "orange": [
        "orange",
        "warning",
        "btn-warning",
        "#ffc107",
        "#ff9800",
        "#e66100",
    ],
}


@dataclass
class MatchResult:
    """Detailed result of matching an element against watcher criteria."""

    matched: bool
    score: float = 0.0
    text: str = ""
    role: str = ""
    bounds: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, width, height
    center: Tuple[int, int] = (0, 0)  # cx, cy
    style_matches: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    element: Any = None  # Reference to the underlying Accessible object


class ButtonMatcher:
    """Evaluates accessibility objects against button rules."""

    def __init__(self, config: WatcherConfig):
        self.config = config
        self._compiled_regex: Optional[re.Pattern] = None
        if self.config.text_match_mode == "regex" and self.config.target_text:
            flags = 0 if self.config.case_sensitive else re.IGNORECASE
            try:
                self._compiled_regex = re.compile(self.config.target_text, flags)
            except re.error:
                self._compiled_regex = None

    def update_config(self, config: WatcherConfig) -> None:
        """Update active configuration."""
        self.config = config
        if self.config.text_match_mode == "regex" and self.config.target_text:
            flags = 0 if self.config.case_sensitive else re.IGNORECASE
            try:
                self._compiled_regex = re.compile(self.config.target_text, flags)
            except re.error:
                self._compiled_regex = None
        else:
            self._compiled_regex = None

    def get_element_text(self, obj: Any, max_depth: int = 3) -> str:
        """Recursively gather text content from an element or its children."""
        try:
            name = (obj.get_name() or "").strip()
            if name:
                return name
        except Exception:
            pass

        try:
            desc = (obj.get_description() or "").strip()
            if desc:
                return desc
        except Exception:
            pass

        if max_depth <= 0:
            return ""

        parts = []
        try:
            child_count = obj.get_child_count()
            for i in range(child_count):
                child = obj.get_child_at_index(i)
                if child:
                    child_text = self.get_element_text(child, max_depth - 1)
                    if child_text:
                        parts.append(child_text)
        except Exception:
            pass

        return " ".join(parts).strip()

    def get_element_attributes(self, obj: Any) -> Dict[str, str]:
        """Extract attributes dictionary from an Accessible object."""
        try:
            attrs = obj.get_attributes()
            if isinstance(attrs, dict):
                return attrs
            if isinstance(attrs, list):
                res = {}
                for item in attrs:
                    if isinstance(item, str) and ":" in item:
                        k, v = item.split(":", 1)
                        res[k.strip()] = v.strip()
                return res
        except Exception:
            pass
        return {}

    def matches_text(self, text: str) -> bool:
        """Check if candidate text satisfies the target text rule."""
        if not text:
            return False

        target = self.config.target_text
        mode = self.config.text_match_mode
        case_sensitive = self.config.case_sensitive

        if not target:
            return False

        c_text = text if case_sensitive else text.lower()
        c_target = target if case_sensitive else target.lower()

        if mode == "exact":
            return c_text == c_target
        elif mode == "contains":
            # Avoid false positives like 'disagree' matching 'agree' or 'disallow' matching 'allow'
            # Check for word-boundary match first (e.g. 'Allow', 'Always Allow', 'Allow Once', 'Agree')
            word_pattern = rf"\b{re.escape(c_target)}\b"
            if re.search(word_pattern, c_text):
                # Ensure it's not explicitly negated (e.g. 'do not allow', "don't allow", 'never allow')
                negation_pattern = rf"\b(not|don't|dont|never|dis|un)\s*{re.escape(c_target)}\b"
                if re.search(negation_pattern, c_text):
                    return False
                return True
            # If target itself has spaces or symbols, check substring
            if " " in c_target and c_target in c_text:
                return True
            return False
        elif mode == "regex":
            if self._compiled_regex:
                return bool(self._compiled_regex.search(text))
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                return bool(re.search(target, text, flags))
            except re.error:
                return False
        return False

    def matches_role(self, role: str) -> bool:
        """Check if candidate role is in allowed roles list."""
        if not role:
            return False
        role_lower = role.lower()
        for allowed in self.config.allowed_roles:
            if allowed.lower() in role_lower:
                return True
        return False

    def inspect_color_and_style(
        self, obj: Any, role: str, text: str, attributes: Dict[str, str]
    ) -> Tuple[bool, float, List[str]]:
        """Inspect element attributes, description, and keywords for style/color match."""
        style_matches: List[str] = []
        score = 0.0

        # Build search space string from attributes, description, and class names
        attr_values = " ".join(f"{k}={v}" for k, v in attributes.items()).lower()
        try:
            description = (obj.get_description() or "").lower()
        except Exception:
            description = ""

        haystack = f"{attr_values} {description} {role.lower()} {text.lower()}"

        target_color_lower = self.config.target_color.lower().strip()
        color_tokens: List[str] = []

        if target_color_lower in COLOR_KEYWORDS:
            color_tokens.extend(COLOR_KEYWORDS[target_color_lower])
        else:
            color_tokens.append(target_color_lower)

        # Also combine with configured style keywords
        all_indicators = set(color_tokens + [kw.lower() for kw in self.config.style_keywords])

        for indicator in all_indicators:
            if not indicator:
                continue
            if indicator in haystack:
                style_matches.append(indicator)
                score += 25.0

        # Special check for GNOME / GTK suggested-action
        if "suggested-action" in haystack or "primary" in haystack:
            score += 50.0

        has_style_match = len(style_matches) > 0
        return has_style_match, score, style_matches

    def evaluate(self, obj: Any) -> MatchResult:
        """Evaluate an element and return detailed MatchResult."""
        try:
            role = obj.get_role_name() or ""
        except Exception:
            return MatchResult(matched=False, reasons=["Cannot get role"])

        if not self.matches_role(role):
            return MatchResult(matched=False, role=role, reasons=[f"Role '{role}' not in allowed roles"])

        # Check states: reject if defunct or explicitly hidden
        try:
            state_set = obj.get_state_set()
            states = {s.value_nick for s in state_set.get_states()}
            if "defunct" in states or "hidden" in states:
                return MatchResult(matched=False, role=role, reasons=["Element is defunct or hidden"])
            if "disabled" in states:
                return MatchResult(matched=False, role=role, reasons=["Element is disabled"])
        except Exception:
            pass

        # Text matching
        text = self.get_element_text(obj)
        if not self.matches_text(text):
            return MatchResult(
                matched=False,
                role=role,
                text=text,
                reasons=[f"Text '{text}' does not match target '{self.config.target_text}'"],
            )

        # Element extents (bounding box)
        bounds = (0, 0, 0, 0)
        center = (0, 0)
        try:
            rect = obj.get_extents(0)  # Atspi.CoordType.SCREEN is 0
            bounds = (rect.x, rect.y, rect.width, rect.height)
            if rect.width > 0 and rect.height > 0:
                center = (rect.x + rect.width // 2, rect.y + rect.height // 2)
        except Exception:
            pass

        # Reject elements that are collapsed or off-screen (e.g. scrolled chat history with negative coordinates)
        if bounds[2] <= 0 or bounds[3] <= 0 or center[0] <= 0 or center[1] <= 0:
            return MatchResult(
                matched=False,
                role=role,
                text=text,
                bounds=bounds,
                center=center,
                reasons=[f"Element is off-screen or zero-sized: bounds={bounds}"],
            )

        # Attributes and style matching
        attributes = self.get_element_attributes(obj)
        has_color_match, style_score, style_matches = self.inspect_color_and_style(
            obj, role, text, attributes
        )

        base_score = 100.0  # Base score for text match
        reasons = [f"Matched text '{text}' with role '{role}'"]

        if self.config.color_mode == "require":
            if not has_color_match:
                return MatchResult(
                    matched=False,
                    role=role,
                    text=text,
                    bounds=bounds,
                    center=center,
                    reasons=["Color/style match required but no matching indicator found"],
                )
            reasons.append(f"Matched style indicators: {style_matches}")
        elif self.config.color_mode == "prefer":
            if has_color_match:
                base_score += style_score + 50.0
                reasons.append(f"Preferred color/style matched: {style_matches}")
            else:
                reasons.append("Color/style did not match, but accepted under 'prefer' mode")
        else:  # 'any'
            reasons.append("Color filtering disabled ('any' mode)")

        return MatchResult(
            matched=True,
            score=base_score + style_score,
            text=text,
            role=role,
            bounds=bounds,
            center=center,
            style_matches=style_matches,
            reasons=reasons,
            element=obj,
        )
