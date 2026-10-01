"""Interactive test dialog for demonstrating and testing the button watcher."""

from __future__ import annotations

import time
from typing import Optional

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk


CSS = b"""
window.test-window {
    background-color: #f8f9fa;
}

label.dialog-title {
    font-size: 16px;
    font-weight: bold;
    color: #212529;
}

label.dialog-desc {
    font-size: 13px;
    color: #495057;
}

button.blue-agree-btn {
    background: linear-gradient(135deg, #007bff, #0056b3);
    color: #ffffff;
    font-weight: bold;
    padding: 8px 24px;
    border-radius: 6px;
    border: none;
    box-shadow: 0 2px 4px rgba(0, 123, 255, 0.3);
}

button.blue-agree-btn:hover {
    background: linear-gradient(135deg, #0069d9, #004085);
}

button.gray-disagree-btn {
    background-color: #e9ecef;
    color: #495057;
    padding: 8px 18px;
    border-radius: 6px;
    border: 1px solid #ced4da;
}

button.red-cancel-btn {
    background-color: #f8d7da;
    color: #721c24;
    padding: 8px 18px;
    border-radius: 6px;
    border: 1px solid #f5c6cb;
}

frame.status-frame {
    background-color: #ffffff;
    border-radius: 6px;
    border: 1px solid #dee2e6;
    padding: 10px;
}
"""


class TestDialog(Gtk.Window):
    """Test dialog containing a blue 'Agree' button for testing."""

    __test__ = False  # Tell pytest this is an app dialog class, not a test suite

    def __init__(self, title: str = "Permission Request (Test Window)"):
        super().__init__(title=title)
        self.set_default_size(440, 260)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class("test-window")

        self.click_count = 0

        # Load CSS
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        self.add(main_box)

        # Header / Title
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title_lbl = Gtk.Label(label="Application Permission Request")
        title_lbl.get_style_context().add_class("dialog-title")
        title_lbl.set_xalign(0.0)

        desc_lbl = Gtk.Label(
            label="An application is requesting permission to proceed. Click Allow to grant "
                  "permission, or Don't Allow to deny."
        )
        desc_lbl.get_style_context().add_class("dialog-desc")
        desc_lbl.set_line_wrap(True)
        desc_lbl.set_xalign(0.0)

        header_box.pack_start(title_lbl, False, False, 0)
        header_box.pack_start(desc_lbl, False, False, 0)
        main_box.pack_start(header_box, False, False, 0)

        # Status frame
        status_frame = Gtk.Frame()
        status_frame.get_style_context().add_class("status-frame")
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        status_box.set_margin_start(8)
        status_box.set_margin_end(8)
        status_box.set_margin_top(8)
        status_box.set_margin_bottom(8)

        self.status_lbl = Gtk.Label(label="Status: Waiting for user action...")
        self.status_lbl.set_xalign(0.0)
        self.counter_lbl = Gtk.Label(label="Allow button clicked: 0 times")
        self.counter_lbl.set_xalign(0.0)

        status_box.pack_start(self.status_lbl, False, False, 0)
        status_box.pack_start(self.counter_lbl, False, False, 0)
        status_frame.add(status_box)
        main_box.pack_start(status_frame, False, False, 0)

        # Button row
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)

        # Cancel button (red)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.get_style_context().add_class("red-cancel-btn")
        cancel_btn.connect("clicked", self._on_cancel_clicked)

        # Deny / Don't Allow button (gray)
        deny_btn = Gtk.Button(label="Don't Allow")
        deny_btn.get_style_context().add_class("gray-disagree-btn")
        deny_btn.connect("clicked", self._on_deny_clicked)

        # Blue Allow button (primary / suggested-action)
        self.allow_btn = Gtk.Button(label="Allow")
        self.allow_btn.get_style_context().add_class("suggested-action")
        self.allow_btn.get_style_context().add_class("blue-agree-btn")
        self.allow_btn.get_accessible().set_description("blue suggested-action primary button")
        self.allow_btn.connect("clicked", self._on_allow_clicked)

        btn_box.pack_start(cancel_btn, False, False, 0)
        btn_box.pack_start(deny_btn, False, False, 0)
        btn_box.pack_start(self.allow_btn, False, False, 0)

        main_box.pack_end(btn_box, False, False, 0)

    def _on_allow_clicked(self, button: Gtk.Button) -> None:
        self.click_count += 1
        t_str = time.strftime("%H:%M:%S")
        self.status_lbl.set_text(f"Status: Allowed at {t_str}! [Auto-clicked]")
        self.counter_lbl.set_text(f"Allow button clicked: {self.click_count} times")

    def _on_deny_clicked(self, button: Gtk.Button) -> None:
        t_str = time.strftime("%H:%M:%S")
        self.status_lbl.set_text(f"Status: Denied at {t_str}")

    def _on_cancel_clicked(self, button: Gtk.Button) -> None:
        t_str = time.strftime("%H:%M:%S")
        self.status_lbl.set_text(f"Status: Canceled at {t_str}")


def launch_test_dialog() -> None:
    """Launch the standalone test dialog."""
    win = TestDialog()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    launch_test_dialog()
