"""
Themeable stylesheet. Two themes (dark/light) and three FX levels
(leggero / medio / pesante).
"""
from __future__ import annotations


# -------- color palettes ----------------------------------------------------

DARK = {
    "root_bg":       "rgba(10, 12, 18, 225)",
    "root_border":   "rgba(255, 255, 255, 28)",
    "titlebar_bg":   "rgba(255, 255, 255, 8)",
    "titlebar_sep":  "rgba(255, 255, 255, 14)",
    "title_color":   "rgba(255, 255, 255, 235)",
    "label_color":   "rgba(255, 255, 255, 215)",
    "muted":         "rgba(255, 255, 255, 130)",
    "section_bg":    "rgba(255, 255, 255, 6)",
    "section_border":"rgba(255, 255, 255, 12)",
    "btn_bg":        "rgba(255, 255, 255, 20)",
    "btn_text":      "rgba(255, 255, 255, 230)",
    "btn_border":    "rgba(255, 255, 255, 26)",
    "btn_hover":     "rgba(255, 255, 255, 40)",
    "btn_press":     "rgba(255, 255, 255, 60)",
    "btn_disabled_bg":"rgba(255, 255, 255, 6)",
    "btn_disabled_text":"rgba(255, 255, 255, 85)",
    "progress_bg":   "rgba(255, 255, 255, 10)",
    "slider_groove": "rgba(255, 255, 255, 18)",
    "slider_handle": "rgba(255, 255, 255, 215)",
    "combo_bg":      "rgba(255, 255, 255, 15)",
    "combo_text":    "rgba(255, 255, 255, 225)",
    "combo_border":  "rgba(255, 255, 255, 26)",
    "combo_pop_bg":  "rgba(14, 17, 24, 248)",
    "dialog_bg":     "rgb(12, 14, 20)",
    "dialog_text":   "rgba(255, 255, 255, 225)",
    "text_edit_bg":  "rgba(6, 8, 12, 235)",
    "text_edit_text":"rgba(220, 230, 240, 230)",
    "menu_bg":       "rgba(14, 17, 24, 250)",
    "menu_text":     "rgba(255, 255, 255, 225)",
    "menu_border":   "rgba(255, 255, 255, 35)",
    "menu_sep":      "rgba(255, 255, 255, 25)",
    "tooltip_bg":    "rgba(16, 18, 26, 248)",
    # Default gradient: graphite-neutral, kept distinct from the "Blue" variant.
    "grad_top":      "rgba(36, 40, 54, 240)",
    "grad_mid":      "rgba(20, 22, 32, 235)",
    "grad_bot":      "rgba(6, 7, 12, 240)",
    "accent":        "#7FD7FF",
}

LIGHT = {
    "root_bg":       "rgba(245, 248, 252, 235)",
    "root_border":   "rgba(0, 0, 0, 60)",
    "titlebar_bg":   "rgba(220, 230, 240, 200)",
    "titlebar_sep":  "rgba(0, 0, 0, 30)",
    "title_color":   "rgba(20, 24, 32, 235)",
    "label_color":   "rgba(20, 24, 32, 220)",
    "muted":         "rgba(20, 24, 32, 130)",
    "section_bg":    "rgba(255, 255, 255, 200)",
    "section_border":"rgba(0, 0, 0, 30)",
    "btn_bg":        "rgba(255, 255, 255, 235)",
    "btn_text":      "rgba(20, 24, 32, 235)",
    "btn_border":    "rgba(0, 0, 0, 40)",
    "btn_hover":     "rgba(127, 215, 255, 90)",
    "btn_press":     "rgba(127, 215, 255, 140)",
    "btn_disabled_bg":"rgba(0, 0, 0, 12)",
    "btn_disabled_text":"rgba(20, 24, 32, 100)",
    "progress_bg":   "rgba(0, 0, 0, 20)",
    "slider_groove": "rgba(0, 0, 0, 30)",
    "slider_handle": "rgba(20, 24, 32, 220)",
    "combo_bg":      "rgba(255, 255, 255, 240)",
    "combo_text":    "rgba(20, 24, 32, 230)",
    "combo_border":  "rgba(0, 0, 0, 40)",
    "combo_pop_bg":  "rgba(248, 250, 254, 250)",
    "dialog_bg":     "rgb(238, 242, 248)",
    "dialog_text":   "rgba(20, 24, 32, 235)",
    "text_edit_bg":  "rgba(255, 255, 255, 240)",
    "text_edit_text":"rgba(20, 24, 32, 235)",
    "menu_bg":       "rgba(248, 250, 254, 250)",
    "menu_text":     "rgba(20, 24, 32, 235)",
    "menu_border":   "rgba(0, 0, 0, 40)",
    "menu_sep":      "rgba(0, 0, 0, 30)",
    "tooltip_bg":    "rgba(28, 32, 44, 245)",
    "grad_top":      "rgba(200, 220, 248, 240)",
    "grad_mid":      "rgba(232, 240, 250, 235)",
    "grad_bot":      "rgba(180, 200, 232, 240)",
    "accent":        "#1f8fc7",
}


# Color variants for "tinta unita" — applied as root_bg override.
SOLID_VARIANTS = {
    "dark": {
        "default":   "rgba(10, 12, 18, 225)",
        "blue":      "rgba(20, 30, 56, 220)",
        "purple":    "rgba(34, 22, 50, 220)",
        "green":     "rgba(18, 36, 28, 220)",
        "graphite":  "rgba(28, 28, 32, 220)",
        # New variants
        "midnight":  "rgba(4, 6, 14, 235)",
        "wine":      "rgba(46, 14, 22, 225)",
        "carbon":    "rgba(8, 8, 10, 235)",
        "lavender":  "rgba(36, 30, 48, 222)",
        "steel":     "rgba(26, 32, 42, 222)",
    },
    "light": {
        "default":  "rgba(245, 248, 252, 235)",
        "blue":     "rgba(225, 236, 250, 235)",
        "purple":   "rgba(238, 230, 248, 235)",
        "green":    "rgba(228, 244, 232, 235)",
        "ivory":    "rgba(248, 244, 232, 235)",
        # New variants
        "cream":    "rgba(250, 242, 226, 235)",
        "sage":     "rgba(228, 236, 224, 235)",
        "apricot":  "rgba(252, 224, 200, 235)",
    },
    # Sepia theme (warm parchment-like)
    "sepia": {
        "default": "rgba(232, 214, 184, 235)",
        "cream":   "rgba(244, 230, 206, 235)",
        "tan":     "rgba(212, 186, 144, 235)",
        "coffee":  "rgba(190, 160, 122, 230)",
    },
    # High-contrast dark theme
    "hicontrast": {
        "default": "rgba(0, 0, 0, 252)",
        "amber":   "rgba(14, 10, 0, 252)",
        "cyan":    "rgba(0, 8, 14, 252)",
    },
    # Solarized base16 palette
    "solarized_dark": {
        "default": "rgba(0, 43, 54, 240)",      # base03
        "base02":  "rgba(7, 54, 66, 240)",
    },
    "solarized_light": {
        "default": "rgba(253, 246, 227, 240)",  # base3
        "base2":   "rgba(238, 232, 213, 240)",
    },
}


# Color variants for gradient — (top, mid, bot) tuples
GRADIENT_VARIANTS = {
    "dark": {
        "default":   ("rgba(36, 40, 54, 240)",  "rgba(20, 22, 32, 235)",  "rgba(6, 7, 12, 240)"),
        "blue":      ("rgba(40, 90, 170, 240)", "rgba(22, 40, 90, 235)",  "rgba(8, 12, 30, 240)"),
        "purple":    ("rgba(100, 50, 140, 240)","rgba(50, 24, 80, 235)",  "rgba(16, 10, 26, 240)"),
        "sunset":    ("rgba(180, 70, 60, 235)", "rgba(90, 38, 70, 230)",  "rgba(20, 14, 30, 240)"),
        "forest":    ("rgba(40, 100, 70, 240)", "rgba(22, 56, 40, 235)",  "rgba(10, 22, 16, 240)"),
        "fire":      ("rgba(200, 90, 30, 235)", "rgba(110, 38, 30, 230)", "rgba(24, 14, 18, 240)"),
        # New variants
        "ocean":     ("rgba(20, 70, 130, 240)", "rgba(10, 50, 95, 235)",  "rgba(4, 24, 50, 240)"),
        "midnight":  ("rgba(20, 22, 40, 245)",  "rgba(10, 10, 22, 240)",  "rgba(2, 2, 8, 245)"),
        "cyberpunk": ("rgba(180, 30, 140, 235)","rgba(50, 20, 90, 230)",  "rgba(8, 12, 60, 240)"),
        "wine":      ("rgba(120, 28, 50, 235)", "rgba(64, 14, 30, 230)",  "rgba(18, 6, 12, 240)"),
        "emerald":   ("rgba(20, 130, 90, 240)", "rgba(12, 70, 50, 235)",  "rgba(4, 22, 18, 240)"),
        "steel":     ("rgba(70, 92, 120, 240)", "rgba(40, 56, 80, 235)",  "rgba(14, 20, 30, 240)"),
        "aurora":    ("rgba(40, 200, 140, 235)","rgba(110, 70, 200, 230)","rgba(220, 90, 160, 235)"),
    },
    "light": {
        "default":   ("rgba(200, 220, 248, 240)","rgba(232, 240, 250, 235)","rgba(180, 200, 232, 240)"),
        "blue":      ("rgba(180, 210, 248, 240)","rgba(220, 234, 250, 235)","rgba(160, 192, 232, 240)"),
        "rose":      ("rgba(252, 220, 232, 240)","rgba(252, 238, 244, 235)","rgba(242, 200, 220, 240)"),
        "mint":      ("rgba(212, 240, 224, 240)","rgba(232, 248, 236, 235)","rgba(192, 224, 208, 240)"),
        "peach":     ("rgba(252, 224, 200, 240)","rgba(252, 238, 220, 235)","rgba(244, 208, 180, 240)"),
        # New variants
        "sky":       ("rgba(190, 220, 248, 240)","rgba(218, 234, 250, 235)","rgba(168, 200, 232, 240)"),
        "sand":      ("rgba(244, 226, 188, 240)","rgba(250, 240, 218, 235)","rgba(232, 208, 168, 240)"),
        "pearl":     ("rgba(238, 234, 244, 240)","rgba(250, 248, 252, 235)","rgba(218, 214, 226, 240)"),
    },
    "sepia": {
        "default": ("rgba(244, 226, 196, 240)", "rgba(232, 214, 184, 235)", "rgba(206, 184, 144, 240)"),
        "warm":    ("rgba(232, 200, 150, 240)", "rgba(218, 188, 138, 235)", "rgba(184, 152, 100, 240)"),
    },
    "hicontrast": {
        "default": ("rgba(8, 8, 8, 252)",   "rgba(0, 0, 0, 252)",   "rgba(0, 0, 0, 252)"),
        "amber":   ("rgba(28, 18, 0, 252)", "rgba(14, 10, 0, 252)", "rgba(0, 0, 0, 252)"),
    },
    "solarized_dark": {
        "default": ("rgba(7, 54, 66, 240)",  "rgba(0, 43, 54, 240)", "rgba(0, 30, 38, 245)"),
    },
    "solarized_light": {
        "default": ("rgba(253, 246, 227, 240)","rgba(238, 232, 213, 235)","rgba(220, 214, 196, 240)"),
    },
}


# Base palettes for the new themes (used when theme != dark|light).
SEPIA = dict(LIGHT)
SEPIA.update({
    "root_bg":       "rgba(232, 214, 184, 235)",
    "root_border":   "rgba(120, 90, 50, 90)",
    "titlebar_bg":   "rgba(232, 214, 184, 220)",
    "titlebar_sep":  "rgba(120, 90, 50, 70)",
    "title_color":   "rgba(60, 40, 20, 235)",
    "label_color":   "rgba(70, 48, 24, 230)",
    "muted":         "rgba(110, 80, 50, 180)",
    "section_bg":    "rgba(250, 238, 214, 200)",
    "section_border":"rgba(140, 100, 60, 90)",
    "btn_bg":        "rgba(250, 238, 214, 235)",
    "btn_text":      "rgba(60, 40, 20, 235)",
    "btn_border":    "rgba(140, 100, 60, 110)",
    "btn_hover":     "rgba(220, 188, 130, 140)",
    "btn_press":     "rgba(200, 162, 100, 170)",
    "combo_bg":      "rgba(252, 244, 224, 245)",
    "combo_text":    "rgba(60, 40, 20, 235)",
    "combo_border":  "rgba(140, 100, 60, 120)",
    "combo_pop_bg":  "rgba(248, 232, 200, 250)",
    "dialog_bg":     "rgb(238, 222, 192)",
    "dialog_text":   "rgba(60, 40, 20, 235)",
    "menu_bg":       "rgba(248, 232, 200, 252)",
    "menu_text":     "rgba(60, 40, 20, 235)",
    "menu_border":   "rgba(140, 100, 60, 120)",
    "menu_sep":      "rgba(120, 90, 50, 80)",
    "tooltip_bg":    "rgba(60, 40, 20, 240)",
    "grad_top":      "rgba(244, 226, 196, 240)",
    "grad_mid":      "rgba(232, 214, 184, 235)",
    "grad_bot":      "rgba(206, 184, 144, 240)",
    "accent":        "#a0522d",
})


HICONTRAST = dict(DARK)
HICONTRAST.update({
    "root_bg":       "rgba(0, 0, 0, 252)",
    "root_border":   "rgba(255, 255, 255, 220)",
    "titlebar_bg":   "rgba(0, 0, 0, 252)",
    "titlebar_sep":  "rgba(255, 255, 255, 180)",
    "title_color":   "rgba(255, 255, 255, 255)",
    "label_color":   "rgba(255, 255, 255, 255)",
    "muted":         "rgba(220, 220, 220, 240)",
    "section_bg":    "rgba(0, 0, 0, 240)",
    "section_border":"rgba(255, 255, 255, 220)",
    "btn_bg":        "rgba(0, 0, 0, 240)",
    "btn_text":      "rgba(255, 255, 255, 255)",
    "btn_border":    "rgba(255, 255, 255, 220)",
    "btn_hover":     "rgba(255, 255, 255, 60)",
    "btn_press":     "rgba(255, 255, 255, 120)",
    "combo_bg":      "rgba(0, 0, 0, 250)",
    "combo_text":    "rgba(255, 255, 255, 255)",
    "combo_border":  "rgba(255, 255, 255, 220)",
    "combo_pop_bg":  "rgba(0, 0, 0, 255)",
    "dialog_bg":     "rgb(0, 0, 0)",
    "dialog_text":   "rgba(255, 255, 255, 255)",
    "menu_bg":       "rgba(0, 0, 0, 255)",
    "menu_text":     "rgba(255, 255, 255, 255)",
    "menu_border":   "rgba(255, 255, 255, 220)",
    "menu_sep":      "rgba(255, 255, 255, 180)",
    "tooltip_bg":    "rgba(0, 0, 0, 255)",
    "grad_top":      "rgba(8, 8, 8, 252)",
    "grad_mid":      "rgba(0, 0, 0, 252)",
    "grad_bot":      "rgba(0, 0, 0, 252)",
    "accent":        "#ffff00",
})


SOLARIZED_DARK = dict(DARK)
SOLARIZED_DARK.update({
    "root_bg":       "rgba(0, 43, 54, 240)",
    "root_border":   "rgba(101, 123, 131, 120)",
    "titlebar_bg":   "rgba(7, 54, 66, 230)",
    "titlebar_sep":  "rgba(88, 110, 117, 130)",
    "title_color":   "rgba(238, 232, 213, 245)",
    "label_color":   "rgba(238, 232, 213, 230)",
    "muted":         "rgba(147, 161, 161, 200)",
    "section_bg":    "rgba(7, 54, 66, 200)",
    "section_border":"rgba(88, 110, 117, 130)",
    "btn_bg":        "rgba(7, 54, 66, 235)",
    "btn_text":      "rgba(238, 232, 213, 235)",
    "btn_border":    "rgba(88, 110, 117, 140)",
    "btn_hover":     "rgba(38, 139, 210, 100)",
    "btn_press":     "rgba(38, 139, 210, 180)",
    "combo_bg":      "rgba(7, 54, 66, 240)",
    "combo_text":    "rgba(238, 232, 213, 235)",
    "combo_border":  "rgba(88, 110, 117, 150)",
    "combo_pop_bg":  "rgba(7, 54, 66, 250)",
    "dialog_bg":     "rgb(0, 43, 54)",
    "dialog_text":   "rgba(238, 232, 213, 235)",
    "menu_bg":       "rgba(7, 54, 66, 252)",
    "menu_text":     "rgba(238, 232, 213, 235)",
    "menu_border":   "rgba(88, 110, 117, 150)",
    "menu_sep":      "rgba(88, 110, 117, 120)",
    "tooltip_bg":    "rgba(0, 43, 54, 250)",
    "grad_top":      "rgba(7, 54, 66, 240)",
    "grad_mid":      "rgba(0, 43, 54, 240)",
    "grad_bot":      "rgba(0, 30, 38, 245)",
    "accent":        "#268bd2",
})


SOLARIZED_LIGHT = dict(LIGHT)
SOLARIZED_LIGHT.update({
    "root_bg":       "rgba(253, 246, 227, 240)",
    "root_border":   "rgba(147, 161, 161, 120)",
    "titlebar_bg":   "rgba(238, 232, 213, 230)",
    "titlebar_sep":  "rgba(147, 161, 161, 130)",
    "title_color":   "rgba(7, 54, 66, 245)",
    "label_color":   "rgba(0, 43, 54, 235)",
    "muted":         "rgba(88, 110, 117, 200)",
    "section_bg":    "rgba(238, 232, 213, 220)",
    "section_border":"rgba(147, 161, 161, 130)",
    "btn_bg":        "rgba(238, 232, 213, 240)",
    "btn_text":      "rgba(7, 54, 66, 235)",
    "btn_border":    "rgba(147, 161, 161, 150)",
    "btn_hover":     "rgba(38, 139, 210, 80)",
    "btn_press":     "rgba(38, 139, 210, 150)",
    "combo_bg":      "rgba(253, 246, 227, 245)",
    "combo_text":    "rgba(7, 54, 66, 235)",
    "combo_border":  "rgba(147, 161, 161, 150)",
    "combo_pop_bg":  "rgba(253, 246, 227, 252)",
    "dialog_bg":     "rgb(253, 246, 227)",
    "dialog_text":   "rgba(7, 54, 66, 235)",
    "menu_bg":       "rgba(253, 246, 227, 252)",
    "menu_text":     "rgba(7, 54, 66, 235)",
    "menu_border":   "rgba(147, 161, 161, 150)",
    "menu_sep":      "rgba(147, 161, 161, 120)",
    "tooltip_bg":    "rgba(0, 43, 54, 245)",
    "grad_top":      "rgba(253, 246, 227, 240)",
    "grad_mid":      "rgba(238, 232, 213, 235)",
    "grad_bot":      "rgba(220, 214, 196, 240)",
    "accent":        "#268bd2",
})


THEME_PALETTES = {
    "dark":             DARK,
    "light":            LIGHT,
    "sepia":            SEPIA,
    "hicontrast":       HICONTRAST,
    "solarized_dark":   SOLARIZED_DARK,
    "solarized_light":  SOLARIZED_LIGHT,
}


def palette_for(theme: str, bg_effect: str, bg_variant: str) -> dict:
    """Return a copy of the palette with grad_*/root_bg replaced by the
    chosen variant (default palette is left untouched)."""
    base = THEME_PALETTES.get(theme, DARK)
    p = dict(base)
    if bg_effect == "gradient":
        v = GRADIENT_VARIANTS.get(theme, {}).get(bg_variant)
        if v:
            p["grad_top"], p["grad_mid"], p["grad_bot"] = v
    elif bg_effect == "none":
        v = SOLID_VARIANTS.get(theme, {}).get(bg_variant)
        if v:
            p["root_bg"] = v
    return p


def _bg_decl(p: dict, bg_effect: str) -> str:
    """Background declaration for the root container."""
    if bg_effect == "gradient":
        # IMPORTANT: must be background-color (not background:) for Qt to honour
        # the gradient on a widget that also has border-radius + a translucent
        # top-level window. The shorthand "background:" silently no-ops here.
        return (
            "background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1, "
            f"stop:0 {p['grad_top']}, "
            f"stop:0.5 {p['grad_mid']}, "
            f"stop:1 {p['grad_bot']});"
        )
    return f"background-color: {p['root_bg']};"


def build_qss(theme: str = "dark", fx_level: str = "light",
              bg_effect: str = "none") -> str:
    """Generate the full QSS for the given theme + effects level."""
    p = THEME_PALETTES.get(theme, DARK)
    bg = _bg_decl(p, bg_effect)

    return f"""
/* rootContainer and QFrame.section are now painted by QPainter
   (see ui/painted_frames.py) for crisp antialiased borders + reliable
   gradient on translucent windows. No QSS background here. */

QFrame#titleBar {{
    background-color: {p['titlebar_bg']};
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
    border-bottom: 1px solid {p['titlebar_sep']};
}}
QLabel#titleLabel {{
    color: {p['title_color']};
    font-weight: 600;
    font-size: 12px;
}}
QPushButton[titleBtn="true"] {{
    background-color: {p['btn_bg']};
    border: none;
    border-radius: 13px;
    color: {p['btn_text']};
}}
QPushButton[titleBtn="true"]:hover {{ background-color: {p['btn_hover']}; }}
QPushButton[titleBtn="true"]:pressed {{ background-color: {p['btn_press']}; }}

QLabel {{ color: {p['label_color']}; font-size: 11px; }}
QLabel.h1 {{ font-size: 28px; font-weight: 700; color: {p['title_color']}; }}
QLabel.h2 {{ font-size: 16px; font-weight: 600; color: {p['title_color']}; }}
QLabel.muted {{ color: {p['muted']}; }}
QLabel.warn  {{ color: #ffb454; }}
QLabel.critical {{ color: #ff5e57; }}
QLabel.ok {{ color: #6ed98a; }}

QFrame.section {{
    /* painted via QPainter in painted_frames.RoundedSection */
}}

QPushButton {{
    background-color: {p['btn_bg']};
    color: {p['btn_text']};
    border: 1px solid {p['btn_border']};
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 11px;
}}
QPushButton:hover  {{ background-color: {p['btn_hover']}; }}
QPushButton:pressed {{ background-color: {p['btn_press']}; }}
QPushButton:disabled {{
    color: {p['btn_disabled_text']};
    background-color: {p['btn_disabled_bg']};
}}
QPushButton.preset {{ padding: 6px 4px; font-weight: 600; }}
QPushButton#preset_silent:checked {{
    background-color: rgba(110, 217, 138, 50);
    border: 2px solid #6ed98a; color: #2c8a44;
}}
QPushButton#preset_balanced:checked {{
    background-color: rgba(127, 215, 255, 50);
    border: 2px solid #7FD7FF; color: #1f6c8c;
}}
QPushButton#preset_performance:checked {{
    background-color: rgba(255, 94, 87, 50);
    border: 2px solid #ff5e57; color: #b03038;
}}

QProgressBar {{
    background-color: {p['progress_bg']};
    border: none; border-radius: 4px;
    text-align: center; color: {p['label_color']};
    font-size: 10px; height: 8px;
}}
QProgressBar::chunk {{
    background-color: rgba(127, 215, 255, 200);
    border-radius: 4px;
}}

QSlider::groove:horizontal {{
    background: {p['slider_groove']}; height: 4px; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {p['slider_handle']};
    width: 12px; height: 12px; margin: -5px 0; border-radius: 6px;
}}

QComboBox, QSpinBox {{
    background-color: {p['combo_bg']}; color: {p['combo_text']};
    border: 1px solid {p['combo_border']}; border-radius: 6px;
    padding: 3px 6px; selection-background-color: rgba(127, 215, 255, 70);
}}
QComboBox QAbstractItemView {{
    background-color: {p['combo_pop_bg']}; color: {p['combo_text']};
    border: 1px solid {p['combo_border']};
    selection-background-color: rgba(127, 215, 255, 100); outline: 0;
}}
QCheckBox {{ color: {p['label_color']}; font-size: 11px; spacing: 6px; }}

QDialog {{ background-color: {p['dialog_bg']}; color: {p['dialog_text']}; }}

QPlainTextEdit, QTextEdit {{
    background-color: {p['text_edit_bg']}; color: {p['text_edit_text']};
    border: 1px solid {p['combo_border']}; border-radius: 8px;
    font-family: "JetBrains Mono", "Cascadia Code", "Consolas", monospace;
    font-size: 10px; selection-background-color: rgba(127, 215, 255, 80);
}}

QToolTip {{
    background-color: {p['tooltip_bg']}; color: rgba(255,255,255,235);
    border: 1px solid {p['menu_border']}; padding: 4px 6px; border-radius: 6px;
}}

QTabWidget::pane {{
    background: transparent;
    border: 1px solid {p['combo_border']};
    border-radius: 8px;
    top: -1px;
}}
QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background-color: {p['btn_bg']};
    color: {p['muted']};
    border: 1px solid {p['btn_border']};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 16px;
    margin-right: 2px;
    min-width: 60px;
}}
QTabBar::tab:hover {{
    background-color: {p['btn_hover']};
    color: {p['btn_text']};
}}
QTabBar::tab:selected {{
    background-color: {p['btn_press']};
    color: {p['title_color']};
    font-weight: 700;
    border: 1px solid {p['combo_border']};
    border-bottom: none;
}}
QTabBar::tab:!selected {{
    margin-top: 3px;
}}

QMenu {{
    background-color: {p['menu_bg']}; color: {p['menu_text']};
    border: 1px solid {p['menu_border']}; border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 5px 18px 5px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background-color: rgba(127, 215, 255, 100); }}
QMenu::separator {{
    height: 1px; background-color: {p['menu_sep']}; margin: 4px 6px;
}}
"""


# Legacy export so any old import still works
QSS = build_qss("dark", "light", "none")
