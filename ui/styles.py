# SPDX-License-Identifier: GPL-3.0-or-later
"""
Themeable stylesheet. Two themes (dark/light) and three FX levels
(leggero / medio / pesante).
"""
from __future__ import annotations


# -------- color palettes ----------------------------------------------------

DARK = {
    "root_bg":       "rgba(14, 17, 24, 252)",
    "root_border":   "rgba(255, 255, 255, 38)",
    "titlebar_bg":   "rgba(255, 255, 255, 12)",
    "titlebar_sep":  "rgba(255, 255, 255, 30)",
    "title_color":   "rgba(255, 255, 255, 245)",
    "label_color":   "rgba(255, 255, 255, 230)",
    "muted":         "rgba(255, 255, 255, 175)",
    "section_bg":    "rgba(24, 28, 38, 255)",
    "section_border":"rgba(255, 255, 255, 32)",
    "btn_bg":        "rgba(255, 255, 255, 24)",
    "btn_text":      "rgba(255, 255, 255, 245)",
    "btn_border":    "rgba(255, 255, 255, 45)",
    "btn_hover":     "rgba(255, 255, 255, 55)",
    "btn_press":     "rgba(255, 255, 255, 80)",
    "btn_disabled_bg":"rgba(255, 255, 255, 8)",
    "btn_disabled_text":"rgba(255, 255, 255, 115)",
    "progress_bg":   "rgba(255, 255, 255, 20)",
    "slider_groove": "rgba(255, 255, 255, 35)",
    "slider_handle": "#7FD7FF",
    "combo_bg":      "rgba(255, 255, 255, 20)",
    "combo_text":    "rgba(255, 255, 255, 240)",
    "combo_border":  "rgba(255, 255, 255, 45)",
    "combo_pop_bg":  "rgba(14, 17, 24, 252)",
    "dialog_bg":     "rgb(12, 14, 20)",
    "dialog_text":   "rgba(255, 255, 255, 240)",
    "text_edit_bg":  "rgba(6, 8, 12, 245)",
    "text_edit_text":"rgba(230, 240, 250, 240)",
    "menu_bg":       "rgba(14, 17, 24, 252)",
    "menu_text":     "rgba(255, 255, 255, 240)",
    "menu_border":   "rgba(255, 255, 255, 45)",
    "menu_sep":      "rgba(255, 255, 255, 35)",
    "menu_item_selected": "rgba(127, 215, 255, 90)",
    "tooltip_bg":    "rgba(18, 22, 32, 250)",
    "tooltip_text":  "#ffffff",
    "scrollbar_handle": "rgba(255, 255, 255, 75)",
    "scrollbar_handle_hover": "rgba(127, 215, 255, 180)",
    "preset_silent_bg": "rgba(46, 160, 67, 45)",
    "preset_silent_border": "#4ecb71",
    "preset_silent_text": "#a6f4bd",
    "preset_balanced_bg": "rgba(31, 143, 199, 45)",
    "preset_balanced_border": "#7fd7ff",
    "preset_balanced_text": "#bfeaff",
    "preset_perf_bg": "rgba(218, 54, 51, 45)",
    "preset_perf_border": "#ff5e57",
    "preset_perf_text": "#ffaba6",
    "view_toggle_bg": "rgba(31, 143, 199, 50)",
    "view_toggle_border": "#7fd7ff",
    "view_toggle_text": "#ffffff",
    # Default gradient: graphite-neutral, kept distinct from the "Blue" variant.
    "grad_top":      "rgba(36, 40, 54, 240)",
    "grad_mid":      "rgba(20, 22, 32, 235)",
    "grad_bot":      "rgba(6, 7, 12, 240)",
    "accent":        "#7FD7FF",
}

LIGHT = {
    "root_bg":       "rgba(242, 245, 250, 255)",
    "root_border":   "rgba(0, 0, 0, 75)",
    "titlebar_bg":   "rgba(225, 234, 245, 240)",
    "titlebar_sep":  "rgba(0, 0, 0, 50)",
    "title_color":   "#0f172a",
    "label_color":   "#1e293b",
    "muted":         "#475569",
    "section_bg":    "rgba(255, 255, 255, 255)",
    "section_border":"rgba(0, 0, 0, 48)",
    "btn_bg":        "rgba(255, 255, 255, 245)",
    "btn_text":      "#0f172a",
    "btn_border":    "rgba(0, 0, 0, 65)",
    "btn_hover":     "rgba(2, 132, 199, 35)",
    "btn_press":     "rgba(2, 132, 199, 75)",
    "btn_disabled_bg":"rgba(0, 0, 0, 15)",
    "btn_disabled_text":"rgba(30, 41, 59, 130)",
    "progress_bg":   "rgba(0, 0, 0, 30)",
    "slider_groove": "rgba(0, 0, 0, 50)",
    "slider_handle": "#0284c7",
    "combo_bg":      "rgba(255, 255, 255, 245)",
    "combo_text":    "#0f172a",
    "combo_border":  "rgba(0, 0, 0, 65)",
    "combo_pop_bg":  "rgba(255, 255, 255, 252)",
    "dialog_bg":     "rgb(241, 245, 249)",
    "dialog_text":   "#0f172a",
    "text_edit_bg":  "rgba(255, 255, 255, 250)",
    "text_edit_text":"#0f172a",
    "menu_bg":       "rgba(255, 255, 255, 252)",
    "menu_text":     "#0f172a",
    "menu_border":   "rgba(0, 0, 0, 65)",
    "menu_sep":      "rgba(0, 0, 0, 40)",
    "menu_item_selected": "rgba(2, 132, 199, 45)",
    "tooltip_bg":    "rgba(15, 23, 42, 248)",
    "tooltip_text":  "#ffffff",
    "scrollbar_handle": "rgba(15, 23, 42, 75)",
    "scrollbar_handle_hover": "rgba(2, 132, 199, 180)",
    "preset_silent_bg": "rgba(46, 160, 67, 35)",
    "preset_silent_border": "#2da44e",
    "preset_silent_text": "#116329",
    "preset_balanced_bg": "rgba(9, 105, 218, 35)",
    "preset_balanced_border": "#0969da",
    "preset_balanced_text": "#0550ae",
    "preset_perf_bg": "rgba(207, 34, 46, 35)",
    "preset_perf_border": "#cf222e",
    "preset_perf_text": "#a40e26",
    "view_toggle_bg": "rgba(9, 105, 218, 35)",
    "view_toggle_border": "#0969da",
    "view_toggle_text": "#0550ae",
    "grad_top":      "rgba(200, 220, 248, 240)",
    "grad_mid":      "rgba(232, 240, 250, 235)",
    "grad_bot":      "rgba(180, 200, 232, 240)",
    "accent":        "#0284c7",
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
    "root_bg":       "rgba(238, 224, 202, 235)",
    "root_border":   "rgba(120, 85, 45, 120)",
    "titlebar_bg":   "rgba(230, 212, 186, 225)",
    "titlebar_sep":  "rgba(120, 85, 45, 90)",
    "title_color":   "#2e1c0c",
    "label_color":   "#3d2612",
    "muted":         "#614327",
    "section_bg":    "rgba(250, 240, 224, 255)",
    "section_border":"rgba(120, 85, 45, 90)",
    "btn_bg":        "rgba(250, 240, 224, 245)",
    "btn_text":      "#2e1c0c",
    "btn_border":    "rgba(120, 85, 45, 120)",
    "btn_hover":     "rgba(160, 82, 45, 40)",
    "btn_press":     "rgba(160, 82, 45, 80)",
    "btn_disabled_bg":"rgba(120, 85, 45, 20)",
    "btn_disabled_text":"rgba(97, 67, 39, 130)",
    "progress_bg":   "rgba(120, 85, 45, 35)",
    "slider_groove": "rgba(120, 85, 45, 60)",
    "slider_handle": "#a0522d",
    "combo_bg":      "rgba(252, 244, 228, 245)",
    "combo_text":    "#2e1c0c",
    "combo_border":  "rgba(120, 85, 45, 120)",
    "combo_pop_bg":  "rgba(250, 238, 218, 252)",
    "dialog_bg":     "rgb(238, 222, 196)",
    "dialog_text":   "#2e1c0c",
    "text_edit_bg":  "rgba(252, 244, 228, 250)",
    "text_edit_text":"#2e1c0c",
    "menu_bg":       "rgba(250, 238, 218, 252)",
    "menu_text":     "#2e1c0c",
    "menu_border":   "rgba(120, 85, 45, 120)",
    "menu_sep":      "rgba(120, 85, 45, 80)",
    "menu_item_selected": "rgba(160, 82, 45, 45)",
    "tooltip_bg":    "rgba(46, 28, 12, 245)",
    "tooltip_text":  "#ffffff",
    "scrollbar_handle": "rgba(80, 50, 25, 90)",
    "scrollbar_handle_hover": "rgba(160, 82, 45, 180)",
    "preset_silent_bg": "rgba(46, 125, 50, 35)",
    "preset_silent_border": "#2e7d32",
    "preset_silent_text": "#1b5e20",
    "preset_balanced_bg": "rgba(160, 82, 45, 35)",
    "preset_balanced_border": "#a0522d",
    "preset_balanced_text": "#6e3415",
    "preset_perf_bg": "rgba(198, 40, 40, 35)",
    "preset_perf_border": "#c62828",
    "preset_perf_text": "#8e1b1b",
    "view_toggle_bg": "rgba(160, 82, 45, 40)",
    "view_toggle_border": "#a0522d",
    "view_toggle_text": "#4a1e05",
    "grad_top":      "rgba(244, 226, 196, 240)",
    "grad_mid":      "rgba(232, 214, 184, 235)",
    "grad_bot":      "rgba(206, 184, 144, 240)",
    "accent":        "#a0522d",
})


HICONTRAST = dict(DARK)
HICONTRAST.update({
    "root_bg":       "rgba(0, 0, 0, 255)",
    "root_border":   "#ffffff",
    "titlebar_bg":   "rgba(12, 12, 12, 255)",
    "titlebar_sep":  "#ffffff",
    "title_color":   "#ffffff",
    "label_color":   "#ffffff",
    "muted":         "#ffff66",
    "section_bg":    "rgba(12, 12, 12, 255)",
    "section_border":"#ffffff",
    "btn_bg":        "rgba(0, 0, 0, 255)",
    "btn_text":      "#ffffff",
    "btn_border":    "#ffffff",
    "btn_hover":     "rgba(255, 255, 255, 70)",
    "btn_press":     "rgba(255, 255, 255, 140)",
    "btn_disabled_bg":"rgba(40, 40, 40, 255)",
    "btn_disabled_text":"#888888",
    "progress_bg":   "rgba(255, 255, 255, 50)",
    "slider_groove": "#ffffff",
    "slider_handle": "#ffff00",
    "combo_bg":      "rgba(0, 0, 0, 255)",
    "combo_text":    "#ffffff",
    "combo_border":  "#ffffff",
    "combo_pop_bg":  "rgba(0, 0, 0, 255)",
    "dialog_bg":     "rgb(0, 0, 0)",
    "dialog_text":   "#ffffff",
    "text_edit_bg":  "rgba(0, 0, 0, 255)",
    "text_edit_text":"#ffffff",
    "menu_bg":       "rgba(0, 0, 0, 255)",
    "menu_text":     "#ffffff",
    "menu_border":   "#ffffff",
    "menu_sep":      "#ffffff",
    "menu_item_selected": "rgba(255, 255, 255, 80)",
    "tooltip_bg":    "rgba(0, 0, 0, 255)",
    "tooltip_text":  "#ffff00",
    "scrollbar_handle": "#ffffff",
    "scrollbar_handle_hover": "#ffff00",
    "preset_silent_bg": "rgba(0, 0, 0, 255)",
    "preset_silent_border": "#00ff66",
    "preset_silent_text": "#00ff66",
    "preset_balanced_bg": "rgba(0, 0, 0, 255)",
    "preset_balanced_border": "#00ffff",
    "preset_balanced_text": "#00ffff",
    "preset_perf_bg": "rgba(0, 0, 0, 255)",
    "preset_perf_border": "#ff4444",
    "preset_perf_text": "#ff6666",
    "view_toggle_bg": "rgba(0, 0, 0, 255)",
    "view_toggle_border": "#ffff00",
    "view_toggle_text": "#ffff00",
    "grad_top":      "rgba(8, 8, 8, 252)",
    "grad_mid":      "rgba(0, 0, 0, 252)",
    "grad_bot":      "rgba(0, 0, 0, 252)",
    "accent":        "#ffff00",
})


SOLARIZED_DARK = dict(DARK)
SOLARIZED_DARK.update({
    "root_bg":       "rgba(0, 43, 54, 240)",
    "root_border":   "#586e75",
    "titlebar_bg":   "rgba(7, 54, 66, 235)",
    "titlebar_sep":  "#586e75",
    "title_color":   "#fdf6e3",
    "label_color":   "#eee8d5",
    "muted":         "#93a1a1",
    "section_bg":    "rgba(7, 54, 66, 255)",
    "section_border":"#586e75",
    "btn_bg":        "rgba(7, 54, 66, 240)",
    "btn_text":      "#eee8d5",
    "btn_border":    "#586e75",
    "btn_hover":     "rgba(38, 139, 210, 100)",
    "btn_press":     "rgba(38, 139, 210, 180)",
    "btn_disabled_bg":"rgba(7, 54, 66, 120)",
    "btn_disabled_text":"#586e75",
    "progress_bg":   "rgba(7, 54, 66, 180)",
    "slider_groove": "#586e75",
    "slider_handle": "#268bd2",
    "combo_bg":      "rgba(7, 54, 66, 240)",
    "combo_text":    "#eee8d5",
    "combo_border":  "#586e75",
    "combo_pop_bg":  "rgba(7, 54, 66, 252)",
    "dialog_bg":     "rgb(0, 43, 54)",
    "dialog_text":   "#eee8d5",
    "text_edit_bg":  "rgba(7, 54, 66, 245)",
    "text_edit_text":"#eee8d5",
    "menu_bg":       "rgba(7, 54, 66, 252)",
    "menu_text":     "#eee8d5",
    "menu_border":   "#586e75",
    "menu_sep":      "#586e75",
    "menu_item_selected": "rgba(38, 139, 210, 100)",
    "tooltip_bg":    "rgba(0, 43, 54, 250)",
    "tooltip_text":  "#fdf6e3",
    "scrollbar_handle": "rgba(147, 161, 161, 120)",
    "scrollbar_handle_hover": "#268bd2",
    "preset_silent_bg": "rgba(133, 153, 0, 45)",
    "preset_silent_border": "#859900",
    "preset_silent_text": "#b8cc29",
    "preset_balanced_bg": "rgba(38, 139, 210, 45)",
    "preset_balanced_border": "#268bd2",
    "preset_balanced_text": "#70bbf2",
    "preset_perf_bg": "rgba(220, 50, 47, 45)",
    "preset_perf_border": "#dc322f",
    "preset_perf_text": "#f77d7a",
    "view_toggle_bg": "rgba(38, 139, 210, 50)",
    "view_toggle_border": "#268bd2",
    "view_toggle_text": "#ffffff",
    "grad_top":      "rgba(7, 54, 66, 240)",
    "grad_mid":      "rgba(0, 43, 54, 240)",
    "grad_bot":      "rgba(0, 30, 38, 245)",
    "accent":        "#268bd2",
})


SOLARIZED_LIGHT = dict(LIGHT)
SOLARIZED_LIGHT.update({
    "root_bg":       "rgba(253, 246, 227, 240)",
    "root_border":   "#93a1a1",
    "titlebar_bg":   "rgba(238, 232, 213, 235)",
    "titlebar_sep":  "#93a1a1",
    "title_color":   "#073642",
    "label_color":   "#002b36",
    "muted":         "#586e75",
    "section_bg":    "rgba(238, 232, 213, 255)",
    "section_border":"#93a1a1",
    "btn_bg":        "rgba(238, 232, 213, 245)",
    "btn_text":      "#073642",
    "btn_border":    "#93a1a1",
    "btn_hover":     "rgba(38, 139, 210, 70)",
    "btn_press":     "rgba(38, 139, 210, 140)",
    "btn_disabled_bg":"rgba(238, 232, 213, 120)",
    "btn_disabled_text":"#93a1a1",
    "progress_bg":   "rgba(238, 232, 213, 180)",
    "slider_groove": "#93a1a1",
    "slider_handle": "#268bd2",
    "combo_bg":      "rgba(253, 246, 227, 245)",
    "combo_text":    "#073642",
    "combo_border":  "#93a1a1",
    "combo_pop_bg":  "rgba(253, 246, 227, 252)",
    "dialog_bg":     "rgb(253, 246, 227)",
    "dialog_text":   "#073642",
    "text_edit_bg":  "rgba(253, 246, 227, 250)",
    "text_edit_text":"#073642",
    "menu_bg":       "rgba(253, 246, 227, 252)",
    "menu_text":     "#073642",
    "menu_border":   "#93a1a1",
    "menu_sep":      "#93a1a1",
    "menu_item_selected": "rgba(38, 139, 210, 70)",
    "tooltip_bg":    "rgba(0, 43, 54, 250)",
    "tooltip_text":  "#fdf6e3",
    "scrollbar_handle": "rgba(88, 110, 117, 120)",
    "scrollbar_handle_hover": "#268bd2",
    "preset_silent_bg": "rgba(133, 153, 0, 35)",
    "preset_silent_border": "#859900",
    "preset_silent_text": "#5b6900",
    "preset_balanced_bg": "rgba(38, 139, 210, 35)",
    "preset_balanced_border": "#268bd2",
    "preset_balanced_text": "#196396",
    "preset_perf_bg": "rgba(220, 50, 47, 35)",
    "preset_perf_border": "#dc322f",
    "preset_perf_text": "#a11f1c",
    "view_toggle_bg": "rgba(38, 139, 210, 35)",
    "view_toggle_border": "#268bd2",
    "view_toggle_text": "#196396",
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
QFrame#titleBar[fullscreen="true"] {{
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
}}

QPushButton.preset {{ padding: 6px 4px; font-weight: 600; }}
QPushButton#preset_silent:checked {{
    background-color: {p['preset_silent_bg']};
    border: 2px solid {p['preset_silent_border']};
    color: {p['preset_silent_text']};
}}
QPushButton#preset_balanced:checked {{
    background-color: {p['preset_balanced_bg']};
    border: 2px solid {p['preset_balanced_border']};
    color: {p['preset_balanced_text']};
}}
QPushButton#preset_performance:checked {{
    background-color: {p['preset_perf_bg']};
    border: 2px solid {p['preset_perf_border']};
    color: {p['preset_perf_text']};
}}

QProgressBar {{
    background-color: {p['progress_bg']};
    border: none; border-radius: 4px;
    text-align: center; color: {p['label_color']};
    font-size: 10px; height: 8px;
}}
QProgressBar::chunk {{
    background-color: {p['accent']};
    border-radius: 4px;
}}

QScrollArea,
QScrollArea#widgetScrollArea,
QScrollArea#widgetScrollArea > QWidget,
QScrollArea#widgetScrollArea > QWidget > QWidget,
QWidget#scrollContent {{
    background: transparent;
    border: none;
}}

QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 6px;
    margin: 4px 1px 4px 0px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background: {p['scrollbar_handle']};
    min-height: 24px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p['scrollbar_handle_hover']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    border: none;
    background: none;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    height: 0px;
    max-height: 0px;
    border: none;
    background: transparent;
}}

QScrollBar::handle:horizontal,
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    height: 0px;
    width: 0px;
    background: none;
    border: none;
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
    background-color: {p['tooltip_bg']}; color: {p['tooltip_text']};
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
QMenu::item:selected {{ background-color: {p['menu_item_selected']}; }}
QMenu::separator {{
    height: 1px; background-color: {p['menu_sep']}; margin: 4px 6px;
}}
"""


def get_semantic_colors(theme: str = "dark") -> dict[str, str]:
    """Returns high-contrast, accessible status and metric colors tailored
    to each theme to ensure WCAG AA readability."""
    if theme in ("light", "solarized_light"):
        return {
            "green": "#166534",
            "cyan":  "#0284c7",
            "blue":  "#0969da",
            "orange":"#b45309",
            "red_orange": "#c2410c",
            "red":   "#cf222e",
        }
    elif theme == "sepia":
        return {
            "green": "#1b5e20",
            "cyan":  "#00695c",
            "blue":  "#0d47a1",
            "orange":"#a0522d",
            "red_orange": "#bf360c",
            "red":   "#b71c1c",
        }
    elif theme == "hicontrast":
        return {
            "green": "#00ff66",
            "cyan":  "#00ffff",
            "blue":  "#00e5ff",
            "orange":"#ffff00",
            "red_orange": "#ff8800",
            "red":   "#ff3333",
        }
    elif theme == "solarized_dark":
        return {
            "green": "#859900",
            "cyan":  "#2aa198",
            "blue":  "#268bd2",
            "orange":"#b58900",
            "red_orange": "#cb4b16",
            "red":   "#dc322f",
        }
    else:  # dark default
        return {
            "green": "#6ed98a",
            "cyan":  "#7FD7FF",
            "blue":  "#7FD7FF",
            "orange":"#ffb454",
            "red_orange": "#ff7a45",
            "red":   "#ff5e57",
        }


def temp_color(temp: float, theme: str = "dark") -> str:
    """Accessible theme-aware color corresponding to temperature band."""
    c = get_semantic_colors(theme)
    if temp < 35:
        return c["cyan"]
    if temp < 55:
        return c["green"]
    if temp < 70:
        return c["cyan"]
    if temp < 85:
        return c["orange"]
    if temp < 95:
        return c["red_orange"]
    return c["red"]


# Legacy export so any old import still works
QSS = build_qss("dark", "light", "none")
