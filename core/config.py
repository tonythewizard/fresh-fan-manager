"""
Persistent user settings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config/fresh-fan-manager"
CONFIG_FILE = CONFIG_DIR / "settings.json"

# Legacy location for migration from previous version
LEGACY_CONFIG_DIR = Path.home() / ".config/macfan-monitor"
LEGACY_CONFIG_FILE = LEGACY_CONFIG_DIR / "settings.json"


@dataclass
class Settings:
    # Appearance
    opacity: float = 0.92
    temp_font_px: int = 60               # user-configurable: 30–80
    theme: str = "dark"                  # "dark" | "light" (round 2)
    bg_effect: str = "gradient"          # "none" | "gradient" | "matrix"
    bg_variant: str = "default"          # variant of solid/gradient palette
    fx_level: str = "light"              # "off" | "light" | "medium" | "heavy" (round 2)
    # Alerts
    alert_temp_c: int = 85
    alert_enabled: bool = True
    # Manual override safety
    manual_safety_temp_c: int = 70
    manual_safety_enabled: bool = True
    # Display server preference (xcb = XWayland, wayland = native)
    display_server: str = "xcb"
    # Window state
    widget_pinned: bool = False
    widget_x: int = -1
    widget_y: int = 40
    window_w: int = 360
    window_h: int = 780
    last_pos_x: int = -1
    last_pos_y: int = -1
    mini_mode: bool = False              # tiny floating mode (just temp + fan)
    mini_x: int = -1
    mini_y: int = -1
    # Misc
    show_top_processes: bool = True
    top_processes_count: int = 5
    top_processes_expanded: bool = False
    active_preset: str = ""

    # Widget system: ordered list of section keys, plus per-section visibility
    widget_order: list[str] = field(default_factory=lambda: [
        "cpu", "fan", "maintenance", "ram", "gpu_battery", "throttle", "disk", "stress",
    ])
    widget_visible: dict[str, bool] = field(default_factory=lambda: {
        "cpu": True, "fan": True, "maintenance": True, "ram": True,
        "gpu_battery": True, "throttle": True, "disk": False, "stress": True,
    })

    def clamped_opacity(self) -> float:
        return max(0.30, min(1.00, self.opacity))

    def clamped_temp_font(self) -> int:
        return max(30, min(80, int(self.temp_font_px)))


def load() -> Settings:
    src = CONFIG_FILE if CONFIG_FILE.exists() else LEGACY_CONFIG_FILE
    if not src.exists():
        return Settings()
    try:
        data = json.loads(src.read_text())
        s = Settings()
        for k, v in data.items():
            if not hasattr(s, k):
                continue
            # Special handling for widget_visible: merge with defaults so new
            # sections introduced after the user's last save are still visible
            if k == "widget_visible" and isinstance(v, dict):
                merged = dict(s.widget_visible)
                for kk, vv in v.items():
                    if isinstance(vv, bool):
                        merged[kk] = vv
                s.widget_visible = merged
                continue
            # widget_order: append any new defaults that aren't in saved list,
            # and drop deprecated keys (e.g. mbpfan, integrated into fan now)
            if k == "widget_order" and isinstance(v, list):
                deprecated = {"mbpfan", "top_procs"}
                saved = [x for x in v if isinstance(x, str) and x not in deprecated]
                for default_key in s.widget_order:
                    if default_key not in saved:
                        saved.append(default_key)
                s.widget_order = saved
                continue
            setattr(s, k, v)
        return s
    except Exception:
        return Settings()


def save(settings: Settings) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(settings), indent=2))
    except Exception:
        pass


def read_display_server_pref() -> str:
    """Read just the display_server setting without instantiating PySide6.
    Called from the entry point BEFORE Qt imports."""
    src = CONFIG_FILE if CONFIG_FILE.exists() else LEGACY_CONFIG_FILE
    if not src.exists():
        return "xcb"
    try:
        data = json.loads(src.read_text())
        v = data.get("display_server", "xcb")
        return v if v in ("xcb", "wayland") else "xcb"
    except Exception:
        return "xcb"
