# Whac-A-Mole 🎯

> **Active-window button watcher and auto-clicker for Linux (Wayland & X11) and macOS.**
> Monitors the active focused window for blue "Allow" buttons (or any configured button) and automatically clicks them.

---

## 🌟 Features

- **Active & Background Window Watching**:
  - Automatically tracks the focused window or specific target windows/tabs.
  - **Works Even When Focus Is Lost**: Specify a **Tab / Window Title Substring** (e.g. `Permissions`, `Meet`, `OAuth`), and Whac-A-Mole will detect and click the target button even when the window or tab is unfocused or runs in the background!
  - `require_focus`: Set to `false` (default) so focus loss never interrupts button clicking.
- **Deep Button Detection**: Uses the Linux Accessibility Bus (**AT-SPI2**) on **Wayland and X11**, and the native **Accessibility API (AXUIElement)** on **macOS**, to reliably inspect window hierarchies, button texts, roles, widget states, and bounding extents. On macOS, Chrome/Electron web content is exposed automatically, DOM class lists feed the color/style heuristics, and a window's default (blue) button is recognised as the primary action.
- **Fully Configurable Target**:
  - **Button Text**: Matches "Allow", "Always Allow", "Agree", "Accept", "OK", or any custom phrase. Supports `contains` (whole-word aware), `exact`, and `regex` modes with optional case sensitivity. Opposing buttons like "Don't Allow" or "Disallow" are safely rejected.
  - **Tab / Window Title**: Matches any substring in the window title or individual browser tabs (e.g., `-s "Permissions"`).
  - **Button Color & Style**: Detects primary blue buttons using color tokens, CSS classes (`suggested-action`, `primary`, `btn-primary`, `btn-blue`, `blue`, `accent`), and custom hex codes (`#007bff`, `#1e88e5`, `#0d6efd`, etc.).
  - **Color Matching Modes**:
    - `prefer`: Prioritizes matching blue buttons if multiple buttons are present, while still allowing fallback.
    - `require`: Strictly requires the button to exhibit the target color/style indicators.
    - `any`: Ignores color constraints and matches any button with the target text.
  - **Allowed Roles**: Customizable widget roles (`push button`, `button`, `link`, `toggle button`).
- **Flexible Click Execution**:
  - `both`: Performs native AT-SPI accessible action + synthesizes physical mouse click.
  - `action`: Triggers native widget action (clean, non-intrusive).
  - `mouse`: Moves and clicks cursor at exact button screen coordinates.
- **Safety & Debounce**:
  - Configurable polling interval (default: `0.5s`).
  - Pre-click delay (default: `0.1s`) so window animations settle.
  - Per-window cooldown (default: `3.0s`) to prevent rapid double-clicks.
  - Max clicks per window (default: `1`).
  - Window title filters & self-exclusion so Whac-A-Mole never clicks its own interface.
  - Simulation mode (`--dry-run`): Log matching buttons without clicking.
- **Dual Interface**:
  - **Modern GTK3 GUI**: Live active window card, styled target button badge preview, real-time activity log, and full settings editor.
  - **Headless CLI / Daemon**: Run as a background service or script in the terminal with `--headless`.
- **Built-in Interactive Test Window**: 1-click test dialog containing a styled blue Allow button, Gray Don't Allow button, and Red Cancel button with live click counters.

---

## 🚀 Quick Start

### 0. Install

**Linux**
```bash
python3 -m venv --system-site-packages .venv   # uses the distro's PyGObject / AT-SPI
.venv/bin/pip install -e .
```

**macOS**
```bash
python3 -m venv .venv
.venv/bin/pip install -e .                     # installs the PyObjC accessibility bindings
```
Then grant your terminal (Terminal, iTerm, VS Code, …) access under
**System Settings → Privacy & Security → Accessibility** — macOS prompts on first start.
The GTK GUI is optional on macOS (`brew install gtk+3 pygobject3`); without it Whac-A-Mole falls
back to headless mode. On macOS the test dialog is a native alert, because GTK widgets are not
visible to the macOS Accessibility API.

### 1. Launch the Graphical Interface
```bash
./run.sh
```
Or with python:
```bash
source .venv/bin/activate
whacamole
```

In the GUI, click **"Open Test Dialog"** to pop up a sample permission window and watch Whac-A-Mole detect and click the blue Allow button!

### 2. Run in Headless CLI Mode
```bash
./run.sh --headless
```

### 3. Test Dialog Only
Launch just the test popup to inspect buttons:
```bash
./run.sh --test-dialog
```

---

## ⚙️ Command-Line Options

```text
usage: whacamole [-h] [-v] [--headless] [--test-dialog] [-t TARGET_TEXT]
                 [-c TARGET_COLOR] [--color-mode {prefer,require,any}]
                 [--match-mode {contains,exact,regex}] [--case-sensitive]
                 [--click-method {both,action,mouse}]
                 [--poll-interval POLL_INTERVAL_SEC] [--cooldown COOLDOWN_SEC]
                 [--dry-run] [--config CONFIG_PATH] [--save-default-config]
```

### Examples

- **Watch for blue "Allow" button in browser tab containing "Permissions" (even when unfocused):**
  ```bash
  ./run.sh --tab-title "Permissions"
  ```

- **Run in headless mode watching a specific tab in the background:**
  ```bash
  ./run.sh --headless --tab-title "Google"
  ```

- **Watch for a green "Accept" button:**
  ```bash
  ./run.sh --text "Accept" --color "green" --color-mode require
  ```

- **Run in simulation mode (dry run) with 1-second polling:**
  ```bash
  ./run.sh --headless --dry-run --poll-interval 1.0
  ```

- **Save default configuration file:**
  ```bash
  ./run.sh --save-default-config
  ```

---

## 📁 Configuration File

Whac-A-Mole loads configuration from `~/.config/whacamole/config.json` (on both Linux and macOS). You can edit this file directly or use the **"Button Configuration"** tab in the GUI.

```json
{
  "target_text": "Allow",
  "text_match_mode": "contains",
  "case_sensitive": false,
  "target_color": "blue",
  "color_mode": "prefer",
  "style_keywords": [
    "suggested-action",
    "primary",
    "btn-primary",
    "btn-blue",
    "blue",
    "accent",
    "action-blue",
    "confirm"
  ],
  "allowed_roles": [
    "push button",
    "button",
    "link",
    "toggle button",
    "menu item"
  ],
  "poll_interval_sec": 0.5,
  "click_delay_sec": 0.1,
  "cooldown_sec": 3.0,
  "click_method": "both",
  "exclude_windows": [
    "Whac-A-Mole",
    "whacamole"
  ],
  "tab_title_substring": "",
  "window_title_filter": "",
  "require_focus": false,
  "auto_raise_window": false,
  "max_clicks_per_window": 1,
  "dry_run": false,
  "desktop_notifications": true,
  "sound_alert": true,
  "auto_start": true
}
```

---

## 🧪 Running Tests

A comprehensive automated test suite covers configuration, text matching, color/style heuristics, watcher debounce, and live GTK auto-clicking:

```bash
.venv/bin/python -m pytest tests/ -v
```

---

## 🛠️ Architecture

```
whacamole/
├── whacamole/
│   ├── config.py         # Configuration dataclass and persistence
│   ├── matcher.py        # Rule engine for text, role, style, and color scoring
│   ├── watcher.py        # Active-window scanner, debounce, and click executor
│   ├── backends/
│   │   ├── atspi.py      # Linux AT-SPI2 backend (Wayland & X11)
│   │   └── macos.py      # macOS Accessibility API backend (PyObjC)
│   ├── gui.py            # Native GTK3 interface and live dashboard
│   ├── cli.py            # Command-line interface and daemon runner
│   ├── test_dialog.py    # Standalone interactive agreement dialog
│   └── __main__.py       # Package entrypoint
├── tests/
│   ├── test_config.py
│   ├── test_matcher.py
│   ├── test_watcher.py
│   ├── test_macos_backend.py
│   └── test_live_dialog_integration.py
├── run.sh                # Executable launcher
├── pyproject.toml
└── README.md
```
