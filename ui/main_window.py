# SPDX-License-Identifier: GPL-3.0-or-later
"""
Fresh Fan Manager — main monitoring window.
Frameless, translucent, with reorderable widget sections.
"""
from __future__ import annotations

import subprocess
from collections import deque
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPoint, QRect, Signal, QEvent
from PySide6.QtGui import (QCursor, QMouseEvent, QWheelEvent, QFont,
                            QGuiApplication, QContextMenuEvent)
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QFrame, QPushButton, QProgressBar,
                                QSizePolicy, QGridLayout, QMenu, QMessageBox,
                                QSlider, QScrollArea)

from core import sensors, mbpfan_ctrl, governor, config, sys_actions
from core.i18n import tr
from core.logger import get_logger
from core.stress import StressTest
from .titlebar import TitleBar
from .sparkline import Sparkline
from .tweaks_dialog import TweaksDialog
from .log_dialog import LogDialog
from .curve_editor import FanCurveDialog
from .preferences_dialog import PreferencesDialog
from .icons import app_icon, GPUCardIcon, BatteryIcon
from .painted_frames import RootFrame, RoundedSection, PaintedButton
from .fit_label import FitLabel
from .widget_manager import WidgetManager, SECTION_LABELS, EssentialsDividerWidget
from .radial_gauge import RadialGauge
from .mini_window import MiniWindow
from .matrix_bg import MatrixBackground
from . import styles as _styles

APP_NAME = "Fresh Fan Manager"
UPDATE_INTERVAL_MS = 1500
DISK_INTERVAL_MS = 30000  # SMART is slow-changing; poll every 30s
HISTORY_LEN = 60
RESIZE_MARGIN = 6

COLOR_GREEN = "#6ed98a"
COLOR_CYAN = "#7FD7FF"
COLOR_ORANGE = "#ffb454"
COLOR_RED_ORANGE = "#ff7a45"
COLOR_RED = "#ff5e57"


def _temp_color(temp: Optional[float], theme: str = "dark") -> str:
    if temp is None:
        return _styles.get_semantic_colors(theme)["cyan"]
    return _styles.temp_color(temp, theme)


class Section(RoundedSection):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 5, 9, 5)
        layout.setSpacing(3)
        self._layout = layout

    def layout(self) -> QVBoxLayout:  # type: ignore[override]
        return self._layout


class ClickableHeader(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            ev.accept()


WINDOW_FIXED_WIDTH = 360


class VerticalOnlyScrollArea(QScrollArea):
    """QScrollArea that strictly restricts scrolling to the vertical axis,
    preventing any lateral or horizontal panning/scrolling."""

    def wheelEvent(self, ev: QWheelEvent) -> None:  # noqa: N802
        delta_y = ev.angleDelta().y()
        if delta_y != 0:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - int(delta_y / 2))
            ev.accept()
        else:
            ev.ignore()


class MainWindow(QWidget):
    quit_requested = Signal()
    widget_mode_changed = Signal(bool)
    temp_updated = Signal(object)
    manual_state_changed = Signal(bool)

    def __init__(self, settings: config.Settings, start_in_widget_mode: bool = False):
        super().__init__()
        self.settings = settings
        self.log = get_logger()
        self._widget_mode = False
        self._manual_mode = False
        self._last_manual_fans: set[int] = set()
        self._notified_high_temp = False
        self._notified_throttle = False
        self._drag_pos: Optional[QPoint] = None
        self._resize_edge: Optional[str] = None
        self._resize_start_geom: Optional[QRect] = None
        self._resize_start_mouse: Optional[QPoint] = None
        self._normal_geom_before_max: Optional[QRect] = None
        self._is_vert_maximized: bool = False
        self._mini: Optional[MiniWindow] = None
        self._top_procs_dialog = None

        self._hist_temp: deque[float] = deque(maxlen=HISTORY_LEN)
        self._hist_fan: deque[float] = deque(maxlen=HISTORY_LEN)
        self._hist_ram: deque[float] = deque(maxlen=HISTORY_LEN)

        # State refs to specific widgets we update from snapshots
        self._refs: dict[str, dict[str, QWidget]] = {}

        self.stress = StressTest(self)
        self.stress.started_at.connect(self._on_stress_started)
        self.stress.progress.connect(self._on_stress_progress)
        self.stress.finished.connect(self._on_stress_finished)

        self._build_ui()
        from .update_controller import UpdateController
        self.updates = UpdateController(self)
        self._height_timer = QTimer(self)
        self._height_timer.setSingleShot(True)
        self._height_timer.setInterval(0)
        self._height_timer.timeout.connect(self._update_min_height)
        self.scroll_content.installEventFilter(self)
        self._apply_window_flags(widget_mode=False)
        self.setFixedWidth(WINDOW_FIXED_WIDTH)
        self.setMinimumHeight(240)
        self.resize(WINDOW_FIXED_WIDTH, settings.window_h)
        self._restore_position()
        self.setWindowOpacity(settings.clamped_opacity())

        self._timer = QTimer(self)
        self._timer.setInterval(UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._disk_timer = QTimer(self)
        self._disk_timer.setInterval(DISK_INTERVAL_MS)
        self._disk_timer.timeout.connect(self._tick_disk)
        self._disk_timer.start()
        sensors.read_cpu_load()

        self._update_button_theme_appearances()
        self._refresh_preset_visual_state()
        self._apply_bg_overlay()

        # After first layout, lock the minimum height to the content size
        # so the user can grow the window but not crush widgets vertically.
        QTimer.singleShot(50, self._update_min_height)
        QTimer.singleShot(300, self._update_min_height)

        # Mini mode if last-saved
        if settings.mini_mode:
            QTimer.singleShot(150, self.enter_mini_mode)
        elif start_in_widget_mode:
            QTimer.singleShot(120, self.enter_widget_mode)

    # ----------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setWindowIcon(app_icon())
        self.setWindowTitle(APP_NAME)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.root = RootFrame(self.settings)
        self.root.setMouseTracking(True)
        outer.addWidget(self.root)

        # Matrix background overlay (created always, only visible if opt-in)
        self.matrix_bg = MatrixBackground(self.root)
        self.matrix_bg.setGeometry(0, 0, self.root.width(), self.root.height())
        self.matrix_bg.hide()
        self.root.installEventFilter(self)

        root_layout = QVBoxLayout(self.root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = TitleBar()
        self.title_bar.title_label.setText(APP_NAME)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_toggle_requested.connect(self._toggle_maximize)
        self.title_bar.close_requested.connect(self.hide)
        self.title_bar.pin_toggle_requested.connect(self.toggle_widget_mode)
        self.title_bar.mini_requested.connect(self.enter_mini_mode)
        root_layout.addWidget(self.title_bar)

        # Edit-mode toolbar (shown only in edit mode)
        self.edit_bar = QFrame()
        self.edit_bar.setObjectName("editBar")
        edit_lay = QHBoxLayout(self.edit_bar)
        edit_lay.setContentsMargins(8, 4, 8, 4)
        info = QLabel(tr("edit_mode_info"))
        info.setStyleSheet("color: rgba(255,255,255,180); font-size: 10px;")
        edit_lay.addWidget(info)
        edit_lay.addStretch()
        self.btn_add_widget = PaintedButton(tr("add_widget"))
        self.btn_add_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_widget.clicked.connect(self._show_add_widget_menu)
        edit_lay.addWidget(self.btn_add_widget)
        self.btn_done_edit = PaintedButton(f"✓ {tr('done_editing')}")
        self.btn_done_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_done_edit.set_checked_appearance("rgba(110,217,138,50)", "#6ed98a", "#6ed98a")
        self.btn_done_edit.setCheckable(True)
        self.btn_done_edit.setChecked(True)
        self.btn_done_edit.clicked.connect(self._toggle_edit_mode)
        edit_lay.addWidget(self.btn_done_edit)
        self.edit_bar.setVisible(False)
        self.edit_bar.setStyleSheet(
            "QFrame#editBar { background: rgba(127,215,255,18); "
            "border-bottom: 1px solid rgba(127,215,255,60); }"
        )
        root_layout.addWidget(self.edit_bar)

        # Segmented view mode toggle: [ ⚡ Essentials ]  [ ★ All Widgets ]
        self.view_bar = QFrame()
        self.view_bar.setObjectName("viewBar")
        view_toggle_row = QHBoxLayout(self.view_bar)
        view_toggle_row.setContentsMargins(10, 4, 10, 4)
        view_toggle_row.setSpacing(6)

        self.btn_view_essentials = PaintedButton(tr("view_mode_essentials"))
        self.btn_view_essentials.setCheckable(True)
        self.btn_view_essentials.setFixedHeight(26)
        self.btn_view_essentials.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_view_essentials.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_essentials.clicked.connect(lambda: self._set_view_mode("essentials"))

        self.btn_view_all = PaintedButton(tr("view_mode_all"))
        self.btn_view_all.setCheckable(True)
        self.btn_view_all.setFixedHeight(26)
        self.btn_view_all.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_view_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_all.clicked.connect(lambda: self._set_view_mode("all"))

        view_toggle_row.addWidget(self.btn_view_essentials, 1)
        view_toggle_row.addWidget(self.btn_view_all, 1)
        root_layout.addWidget(self.view_bar)

        # Smooth, transparent scroll area for widget cards — strictly vertical only
        self.scroll_area = VerticalOnlyScrollArea()
        self.scroll_area.setObjectName("widgetScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setAutoFillBackground(False)
        self.scroll_area.viewport().setAutoFillBackground(False)
        self.scroll_area.horizontalScrollBar().setEnabled(False)
        self.scroll_area.horizontalScrollBar().setRange(0, 0)

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("scrollContent")
        self.scroll_content.setAutoFillBackground(False)
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(8, 2, 10, 4)
        self.scroll_layout.setSpacing(5)

        # Widget container — holds all reorderable sections
        self.widget_container_layout = QVBoxLayout()
        self.widget_container_layout.setSpacing(5)
        self.widget_container_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.addLayout(self.widget_container_layout)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.scroll_content)
        root_layout.addWidget(self.scroll_area, 1)

        # Hook up the widget manager with section builders
        builders = {
            "cpu":                  self._build_cpu_section,
            "fan":                  self._build_fan_section,
            "power":                self._build_power_section,
            "quick_controls":       self._build_quick_controls_section,
            "__essentials_divider__": self._build_essentials_divider,
            "network":              self._build_network_section,
            "cpu_cores":            self._build_cpu_cores_section,
            "ram":                  self._build_ram_section,
            "gpu_battery":          self._build_gpu_battery_section,
            "throttle":             self._build_throttle_section,
            "disk":                 self._build_disk_section,
            "stress":               self._build_stress_section,
            "maintenance":          self._build_maintenance_section,
        }
        self.widgets = WidgetManager(self.settings,
                                     self.widget_container_layout,
                                     builders)
        self.widgets.layout_changed.connect(self._reattach_refs)
        self.widgets.edit_mode_changed.connect(self._on_edit_mode_changed)
        self._refresh_view_toggle()

        # Pinned Footer: alert (sx) — preferenze — log — modifica layout (dx)
        self.footer_bar = QFrame()
        self.footer_bar.setObjectName("footerBar")
        foot = QHBoxLayout(self.footer_bar)
        foot.setSpacing(4)
        foot.setContentsMargins(8, 4, 8, 6)
        self.btn_alert = PaintedButton(self._alert_btn_text())
        self.btn_alert.setToolTip(tr("temp_alert_threshold_tip"))
        self.btn_alert.clicked.connect(self._open_preferences)
        foot.addWidget(self.btn_alert)
        foot.addStretch()
        self.btn_prefs = PaintedButton(f"⚙ {tr('preferences')}")
        self.btn_prefs.clicked.connect(self._open_preferences)
        foot.addWidget(self.btn_prefs)
        self.btn_show_log = PaintedButton("Log")
        self.btn_show_log.clicked.connect(self._open_log)
        foot.addWidget(self.btn_show_log)
        self.btn_edit_layout = PaintedButton("🔧")
        self.btn_edit_layout.setToolTip(tr("edit_layout_tip"))
        self.btn_edit_layout.setFixedWidth(34)
        self.btn_edit_layout.clicked.connect(self._toggle_edit_mode)
        foot.addWidget(self.btn_edit_layout)
        root_layout.addWidget(self.footer_bar)

    # -------------------------------------------------- section builders
    def _make_refs(self, key: str) -> dict[str, QWidget]:
        d: dict[str, QWidget] = {}
        self._refs[key] = d
        return d

    def _build_cpu_section(self) -> QWidget:
        sec = Section()
        r = self._make_refs("cpu")

        header_widget = ClickableHeader()
        header_widget.clicked.connect(self._open_top_processes)
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        h_label = QLabel("CPU")
        h_label.setStyleSheet("font-size:13px; font-weight:600;")
        header.addWidget(h_label)
        r["device"] = QLabel("")
        r["device"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px; font-weight: 500; margin-left: 6px;")
        header.addWidget(r["device"])
        header.addStretch()
        r["load"] = QLabel("load — %")
        r["load"].setStyleSheet("color: rgba(255,255,255,170); font-size: 11px;")
        header.addWidget(r["load"])
        # Open-in-popup indicator
        r["indicator"] = QLabel("⤴")
        r["indicator"].setStyleSheet(
            f"color: {COLOR_CYAN}; font-size: 14px; font-weight: 700; "
            "margin-left: 8px; padding: 0 2px;"
        )
        r["indicator"].setToolTip(tr("top_processes_popup_tip"))
        header.addWidget(r["indicator"])
        sec.layout().addWidget(header_widget)

        r["temp"] = QLabel("—")
        r["temp"].setProperty("_skip_retint", True)
        r["temp"].setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_temp_font(r["temp"])
        sec.layout().addWidget(r["temp"])

        r["spark"] = Sparkline(capacity=HISTORY_LEN, color=COLOR_CYAN)
        r["spark"].set_range(30, 100)
        r["spark"].setMinimumHeight(26)
        r["spark"].setMaximumHeight(26)
        sec.layout().addWidget(r["spark"])

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        r["freq"] = QLabel("— MHz")
        r["freq"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        bottom.addWidget(r["freq"])
        r["cores"] = QLabel("core: —")
        r["cores"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        bottom.addWidget(r["cores"])
        bottom.addStretch()
        r["gov"] = PaintedButton("Balanced")
        r["gov"].setObjectName("governorBtn")
        r["gov"]._padding_h = 6
        r["gov"]._font_px = 10
        r["gov"]._compute_size()
        r["gov"].setCursor(Qt.CursorShape.PointingHandCursor)
        r["gov"].setToolTip(tr("change_cpu_profile"))
        r["gov"].clicked.connect(self._show_governor_menu)
        bottom.addWidget(r["gov"])
        sec.layout().addLayout(bottom)
        return sec

    # Fixed temperature font size (no longer user-configurable)
    TEMP_FONT_PX = 35

    def _apply_temp_font(self, lbl: QLabel) -> None:
        """Apply the fixed 35px temperature font. Must use inline stylesheet
        because the global QSS sets QLabel{font-size:11px} which would
        otherwise override setFont()."""
        size = self.TEMP_FONT_PX
        f = QFont(lbl.font())
        f.setPixelSize(size)
        f.setBold(True)
        lbl.setFont(f)
        lbl.setProperty("_temp_px", size)
        lbl.setMinimumHeight(int(size * 1.05))
        lbl.setMaximumHeight(int(size * 1.4))
        lbl.updateGeometry()
        lbl.setStyleSheet(f"font-size: {size}px; font-weight: 700; padding: 0px;")

    def _build_fan_section(self) -> QWidget:
        sec = Section()
        r = self._make_refs("fan")
        # Header: title + RPM (right) + status badge (right)
        ftitle = QHBoxLayout()
        f_h = QLabel(tr("fan_title")); f_h.setStyleSheet("font-size:13px; font-weight:600;")
        ftitle.addWidget(f_h)
        r["status"] = QLabel("—")
        r["status"].setStyleSheet("font-size: 10px; margin-left: 6px;")
        ftitle.addWidget(r["status"])
        ftitle.addStretch()
        r["rpm"] = QLabel("— RPM"); r["rpm"].setStyleSheet("font-size:14px; font-weight:600;")
        ftitle.addWidget(r["rpm"])
        sec.layout().addLayout(ftitle)

        r["bar"] = QProgressBar(); r["bar"].setRange(0, 100); r["bar"].setTextVisible(False)
        sec.layout().addWidget(r["bar"])

        frow = QHBoxLayout()
        frow.setContentsMargins(0, 0, 0, 0)
        r["minmax"] = QLabel("min — / max —")
        r["minmax"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        frow.addWidget(r["minmax"]); frow.addStretch()
        r["spark"] = Sparkline(capacity=HISTORY_LEN, color="#a78bfa")
        # Hard-fix the sparkline height so it cannot bleed onto the preset row
        # below it (the Sparkline custom widget otherwise honours its own
        # sizeHint and the row grows when the section is laid out vertically).
        r["spark"].setFixedHeight(18)
        r["spark"].setMinimumWidth(70)
        r["spark"].setMaximumWidth(160)
        frow.addWidget(r["spark"], 1)
        sec.layout().addLayout(frow)

        # Multi-fan detail row for dual/triple fan laptops (CPU + GPU fans)
        r["multi_fans"] = QLabel("")
        r["multi_fans"].setStyleSheet("color: rgba(255,255,255,160); font-size: 10px; padding-top: 2px;")
        r["multi_fans"].setVisible(False)
        sec.layout().addWidget(r["multi_fans"])

        # ----- Integrated profile presets (formerly mbpfan section) -----
        preset_row = QHBoxLayout(); preset_row.setSpacing(4)
        preset_row.setContentsMargins(0, 6, 0, 0)
        p_th = _styles.THEME_PALETTES.get(self.settings.theme, _styles.DARK)
        r["btn_silent"] = PaintedButton("Silent")
        r["btn_balanced"] = PaintedButton("Balanced")
        r["btn_perf"] = PaintedButton("Perform.")
        r["btn_silent"].set_checked_appearance(
            p_th["preset_silent_bg"], p_th["preset_silent_border"], p_th["preset_silent_text"])
        r["btn_balanced"].set_checked_appearance(
            p_th["preset_balanced_bg"], p_th["preset_balanced_border"], p_th["preset_balanced_text"])
        r["btn_perf"].set_checked_appearance(
            p_th["preset_perf_bg"], p_th["preset_perf_border"], p_th["preset_perf_text"])
        self._preset_buttons = {
            "Silent":      r["btn_silent"],
            "Balanced":    r["btn_balanced"],
            "Performance": r["btn_perf"],
        }
        for name, b in self._preset_buttons.items():
            b.setCheckable(True)
            # Tighter padding so 3 buttons fit on a narrow window
            b._padding_h = 4
            b._compute_size()
            b.clicked.connect(lambda _=False, n=name: self._apply_preset(n))
            preset_row.addWidget(b, 1)  # stretch=1 so they share width equally
        sec.layout().addLayout(preset_row)

        adv_row = QHBoxLayout(); adv_row.setSpacing(4)
        r["btn_curve"] = PaintedButton(tr("curve_btn")); r["btn_curve"].clicked.connect(self._open_curve)
        r["btn_tweaks"] = PaintedButton(tr("tweaks_btn")); r["btn_tweaks"].clicked.connect(self._open_tweaks)
        r["btn_restart"] = PaintedButton(tr("restart")); r["btn_restart"].clicked.connect(self._restart_mbpfan)
        r["btn_install"] = PaintedButton(tr("install_service"))
        r["btn_install"].clicked.connect(self._install_mbpfan)
        r["btn_install"].setVisible(False)
        for b in (r["btn_curve"], r["btn_tweaks"], r["btn_restart"]):
            b._padding_h = 4
            b._compute_size()
            adv_row.addWidget(b, 1)
        adv_row.addWidget(r["btn_install"])
        sec.layout().addLayout(adv_row)

        # ----- Manual override -----
        manual_header = QHBoxLayout()
        manual_header.setContentsMargins(0, 4, 0, 0)
        ml = QLabel(tr("fan_manual_override"))
        ml.setStyleSheet("color: rgba(255,255,255,200); font-size: 11px; font-weight: 600;")
        manual_header.addWidget(ml); manual_header.addStretch()
        r["badge"] = QLabel("OFF")
        r["badge"].setStyleSheet(
            "color: rgba(255,255,255,140); background: rgba(255,255,255,12); "
            "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
        )
        manual_header.addWidget(r["badge"])
        r["toggle"] = PaintedButton(tr("activate"))
        r["toggle"].setCheckable(True); r["toggle"].setFixedWidth(78)
        r["toggle"].toggled.connect(self._toggle_manual)
        manual_header.addWidget(r["toggle"])
        sec.layout().addLayout(manual_header)

        r["row"] = QWidget()
        manual_row_layout = QHBoxLayout(r["row"])
        manual_row_layout.setContentsMargins(0, 2, 0, 0)
        manual_row_layout.setSpacing(8)
        fans = sensors.read_fans()
        fan_min = fans[0].min_rpm if fans else 1200
        fan_max = fans[0].max_rpm if fans else 6500
        self._fan_min_rpm = fan_min
        self._fan_max_rpm = fan_max
        r["slider"] = QSlider(Qt.Orientation.Horizontal)
        r["slider"].setRange(fan_min, fan_max)
        r["slider"].setSingleStep(50); r["slider"].setPageStep(200)
        r["slider"].setValue(fan_min)
        manual_row_layout.addWidget(r["slider"], 1)
        r["rpm_lbl"] = QLabel(f"{fan_min} RPM")
        r["rpm_lbl"].setStyleSheet(f"color: {COLOR_CYAN}; font-weight: 600; font-size: 11px;")
        r["rpm_lbl"].setFixedWidth(78)
        r["rpm_lbl"].setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        manual_row_layout.addWidget(r["rpm_lbl"])
        r["row"].setVisible(False)
        sec.layout().addWidget(r["row"])

        self._manual_debounce = QTimer(self)
        self._manual_debounce.setSingleShot(True)
        self._manual_debounce.setInterval(300)
        self._manual_debounce.timeout.connect(self._apply_manual_rpm)
        r["slider"].valueChanged.connect(self._on_slider_changed)
        return sec

    def _build_ram_section(self) -> QWidget:
        sec = Section()
        r = self._make_refs("ram")
        rtitle = QHBoxLayout()
        rh = QLabel("RAM"); rh.setStyleSheet("font-size:13px; font-weight:600;")
        rtitle.addWidget(rh); rtitle.addStretch()
        r["lbl"] = QLabel("— / —"); r["lbl"].setStyleSheet("font-size:13px; font-weight:600;")
        rtitle.addWidget(r["lbl"])
        sec.layout().addLayout(rtitle)
        r["bar"] = QProgressBar(); r["bar"].setRange(0, 100); r["bar"].setTextVisible(False)
        sec.layout().addWidget(r["bar"])
        rrow = QHBoxLayout()
        r["detail"] = QLabel(f"{tr('ram_used')} — · {tr('ram_avail')} — · swap —")
        r["detail"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        rrow.addWidget(r["detail"]); rrow.addStretch()
        r["spark"] = Sparkline(capacity=HISTORY_LEN, color=COLOR_GREEN)
        r["spark"].set_range(0, 100)
        r["spark"].setFixedHeight(18)
        r["spark"].setMinimumWidth(70)
        r["spark"].setMaximumWidth(160)
        rrow.addWidget(r["spark"], 1)
        sec.layout().addLayout(rrow)
        return sec

    def _build_maintenance_section(self) -> QWidget:
        sec = Section()
        r = self._make_refs("maintenance")
        h = QLabel(tr("sec_maintenance"))
        h.setStyleSheet("font-size:13px; font-weight:600;")
        sec.layout().addWidget(h)
        info = QLabel(
            "Free system caches or run thorough cleaning."
            if tr("save") == "Save" else
            "Libera cache di sistema o esegui una pulizia approfondita."
        )
        info.setStyleSheet("color: rgba(255,255,255,150); font-size: 10px;")
        info.setWordWrap(True)
        sec.layout().addWidget(info)
        row = QHBoxLayout(); row.setSpacing(6)
        r["free_btn"] = PaintedButton(f"🧹 {tr('free_ram')}")
        r["free_btn"].setToolTip(
            "Runs 'sync' + drop_caches=3 to release memory caches."
            if tr("save") == "Save" else
            "Esegue 'sync' + drop_caches=3 — libera cache pagina, dentries e inodes."
        )
        r["free_btn"].setCursor(Qt.CursorShape.PointingHandCursor)
        r["free_btn"].clicked.connect(self._free_ram)
        row.addWidget(r["free_btn"], 1)
        r["cleanup_btn"] = PaintedButton(f"🧽 {tr('clean_system')}")
        r["cleanup_btn"].setToolTip(
            "Clean logs, package cache, user cache, thumbnails, trash."
            if tr("save") == "Save" else
            "Pulizia di log di sistema, cache pacchetti, cache utente, thumbnail, cestino."
        )
        r["cleanup_btn"].setCursor(Qt.CursorShape.PointingHandCursor)
        r["cleanup_btn"].clicked.connect(self._open_cleanup)
        row.addWidget(r["cleanup_btn"], 1)
        sec.layout().addLayout(row)
        return sec

    def _build_gpu_battery_section(self) -> QWidget:
        wrap = QWidget()
        hl = QHBoxLayout(wrap); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(6)

        # ------- GPU -------
        gpu_sec = Section()
        rg = self._make_refs("gpu")
        # Card layout: title at top, icon+temp row in the middle, freq below
        # Header: title
        gh = QLabel("GPU")
        gh.setStyleSheet("font-size: 13px; font-weight: 600;")
        gpu_sec.layout().addWidget(gh)

        # Centre row: icon (left) + big coloured temperature (right, centred)
        centre_row = QHBoxLayout()
        centre_row.setContentsMargins(0, 2, 0, 2)
        centre_row.setSpacing(8)
        rg["icon"] = GPUCardIcon()
        rg["icon"].setFixedSize(44, 44)
        centre_row.addWidget(rg["icon"], 0, Qt.AlignmentFlag.AlignVCenter)
        rg["temp"] = QLabel("—°")
        rg["temp"].setProperty("_skip_retint", True)
        rg["temp"].setAlignment(Qt.AlignmentFlag.AlignCenter)
        rg["temp"].setStyleSheet(
            "color: rgba(255,255,255,235); font-size: 26px; font-weight: 700; padding: 0px;"
        )
        centre_row.addWidget(rg["temp"], 1)
        gpu_sec.layout().addLayout(centre_row)

        # Footer: frequency line
        rg["freq"] = QLabel("— MHz")
        rg["freq"].setAlignment(Qt.AlignmentFlag.AlignCenter)
        rg["freq"].setWordWrap(True)
        rg["freq"].setStyleSheet(
            "color: rgba(255,255,255,200); font-size: 11px; font-weight: 600; padding: 0px;"
        )
        gpu_sec.layout().addWidget(rg["freq"])
        hl.addWidget(gpu_sec, 1)

        # ------- Battery -------
        bat_sec = Section()
        rb = self._make_refs("battery")
        top_row2 = QHBoxLayout(); top_row2.setContentsMargins(0, 0, 0, 0); top_row2.setSpacing(6)
        title_col2 = QVBoxLayout(); title_col2.setSpacing(0)
        bh = QLabel(tr("battery_title")); bh.setStyleSheet("font-size: 13px; font-weight: 600;")
        title_col2.addWidget(bh)
        rb["pct"] = FitLabel("— %", max_px=22, min_px=14)
        rb["pct"].setStyleSheet("color: rgba(255,255,255,235); padding: 0px;")
        title_col2.addWidget(rb["pct"])
        top_row2.addLayout(title_col2, 1)
        rb["icon"] = BatteryIcon()
        rb["icon"].setFixedSize(34, 48)
        top_row2.addWidget(rb["icon"], 0, Qt.AlignmentFlag.AlignVCenter)
        bat_sec.layout().addLayout(top_row2)
        # Details: status / temp on one row, salute / cicli on another
        det1 = QHBoxLayout(); det1.setSpacing(6); det1.setContentsMargins(0, 2, 0, 0)
        rb["status"] = QLabel("—")
        rb["status"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        rb["temp"] = QLabel("— °C")
        rb["temp"].setProperty("_skip_retint", True)
        rb["temp"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        det1.addWidget(rb["status"]); det1.addStretch(); det1.addWidget(rb["temp"])
        bat_sec.layout().addLayout(det1)
        det2 = QHBoxLayout(); det2.setSpacing(4); det2.setContentsMargins(0, 0, 0, 0)
        rb["health"] = QLabel("—")
        rb["health"].setProperty("_skip_retint", True)
        rb["health"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        rb["cycles"] = QLabel("—")
        rb["cycles"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        det2.addWidget(rb["health"]); det2.addStretch(); det2.addWidget(rb["cycles"])
        bat_sec.layout().addLayout(det2)
        hl.addWidget(bat_sec, 1)
        return wrap

    def _build_throttle_section(self) -> QWidget:
        sec = Section()
        r = self._make_refs("throttle")
        title = QHBoxLayout()
        h = QLabel(f"⚡ {tr('throttle_title')}")
        h.setStyleSheet("font-size:13px; font-weight:600;")
        title.addWidget(h); title.addStretch()
        r["badge"] = QLabel("OK")
        r["badge"].setStyleSheet(
            f"color: {COLOR_GREEN}; background: rgba(110,217,138,30); "
            "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
        )
        title.addWidget(r["badge"])
        sec.layout().addLayout(title)
        r["counts"] = QLabel("package: 0 · core: 0")
        r["counts"].setStyleSheet("color: rgba(255,255,255,160); font-size: 11px;")
        sec.layout().addWidget(r["counts"])
        r["last"] = QLabel(tr("throttle_no_events"))
        r["last"].setStyleSheet("color: rgba(255,255,255,130); font-size: 10px;")
        sec.layout().addWidget(r["last"])
        return sec

    def _build_disk_section(self) -> QWidget:
        sec = Section()
        sec.layout().setContentsMargins(9, 5, 9, 5)
        sec.layout().setSpacing(3)
        r = self._make_refs("disk")

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        h = QLabel(f"💾 {tr('disk_title')}")
        h.setStyleSheet("font-size:13px; font-weight:600;")
        hdr.addWidget(h)
        hdr.addStretch()
        r["temp"] = QLabel("—")
        r["temp"].setProperty("_skip_retint", True)
        r["temp"].setStyleSheet("color: rgba(255,255,255,140); font-size: 11px; font-weight: 600;")
        hdr.addWidget(r["temp"])
        sec.layout().addLayout(hdr)

        r["model"] = QLabel(tr("disk_detecting"))
        r["model"].setStyleSheet("color: rgba(255,255,255,170); font-size: 11px;")
        sec.layout().addWidget(r["model"])

        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(0, 1, 0, 0)
        r["health"] = QLabel("SMART —")
        r["health"].setProperty("_skip_retint", True)
        r["health"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        sub_row.addWidget(r["health"])
        sub_row.addStretch()
        r["stats"] = QLabel(f"{tr('disk_hours')} — · {tr('disk_cycles')} —")
        r["stats"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        sub_row.addWidget(r["stats"])
        sec.layout().addLayout(sub_row)
        return sec

    def _build_stress_section(self) -> QWidget:
        sec = Section()
        # Tighter padding only — content is fully preserved
        sec.layout().setContentsMargins(9, 4, 9, 4)
        sec.layout().setSpacing(3)
        r = self._make_refs("stress")
        title = QHBoxLayout(); title.setSpacing(6)
        h = QLabel(tr("stress_title")); h.setStyleSheet("font-size:13px; font-weight:600;")
        title.addWidget(h); title.addStretch()
        r["status"] = QLabel(tr("stress_idle"))
        r["status"].setProperty("_skip_retint", True)
        r["status"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        title.addWidget(r["status"])
        sec.layout().addLayout(title)

        row = QHBoxLayout(); row.setSpacing(5)
        r["btn30"] = PaintedButton("30 s")
        r["btn60"] = PaintedButton("60 s")
        r["btn90"] = PaintedButton("90 s")
        for b, d in ((r["btn30"], 30), (r["btn60"], 60), (r["btn90"], 90)):
            b.clicked.connect(lambda _=False, dd=d: self._start_stress(dd))
            row.addWidget(b)
        r["btn_stop"] = PaintedButton("Stop")
        r["btn_stop"].setVisible(False)
        r["btn_stop"].clicked.connect(self._stop_stress)
        row.addWidget(r["btn_stop"])
        sec.layout().addLayout(row)
        r["bar"] = QProgressBar()
        r["bar"].setRange(0, 100); r["bar"].setValue(0); r["bar"].setTextVisible(False)
        r["bar"].setFixedHeight(6)
        r["bar"].setVisible(False)
        sec.layout().addWidget(r["bar"])
        return sec

    def _build_network_section(self) -> QWidget:
        sec = Section()
        sec.layout().setContentsMargins(9, 4, 9, 4)
        sec.layout().setSpacing(3)
        r = self._make_refs("network")

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        t = QLabel(tr("sec_network"))
        t.setStyleSheet("font-size:12px; font-weight:600;")
        hdr.addWidget(t)

        r["iface"] = QLabel("—")
        r["iface"].setStyleSheet(
            f"color: {COLOR_CYAN}; background: rgba(127,215,255,20); "
            "border-radius: 4px; padding: 1px 5px; font-size: 9px; font-weight: 700; margin-left: 4px;"
        )
        hdr.addWidget(r["iface"])
        hdr.addStretch()

        r["wifi"] = QLabel("")
        r["wifi"].setStyleSheet("color: rgba(255,255,255,160); font-size: 10px;")
        hdr.addWidget(r["wifi"])
        sec.layout().addLayout(hdr)

        rates_row = QHBoxLayout()
        rates_row.setContentsMargins(0, 2, 0, 0)
        rates_row.setSpacing(12)

        r["down_rate"] = QLabel("↓ 0.0 KB/s")
        r["down_rate"].setStyleSheet(f"color: {COLOR_CYAN}; font-size: 13px; font-weight: 700;")
        rates_row.addWidget(r["down_rate"])

        r["up_rate"] = QLabel("↑ 0.0 KB/s")
        r["up_rate"].setStyleSheet(f"color: {COLOR_GREEN}; font-size: 13px; font-weight: 700;")
        rates_row.addWidget(r["up_rate"])
        rates_row.addStretch()

        r["band"] = QLabel("")
        r["band"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        rates_row.addWidget(r["band"])
        sec.layout().addLayout(rates_row)

        r["sparks_container"] = QWidget()
        spk_lay = QHBoxLayout(r["sparks_container"])
        spk_lay.setContentsMargins(0, 2, 0, 0)
        spk_lay.setSpacing(6)

        r["spark_down"] = Sparkline(capacity=HISTORY_LEN, color=COLOR_CYAN)
        r["spark_down"].setFixedHeight(18)
        spk_lay.addWidget(r["spark_down"], 1)

        r["spark_up"] = Sparkline(capacity=HISTORY_LEN, color=COLOR_GREEN)
        r["spark_up"].setFixedHeight(18)
        spk_lay.addWidget(r["spark_up"], 1)
        sec.layout().addWidget(r["sparks_container"])

        def set_density(size: str):
            is_compact = (size == "compact")
            is_exp = (size == "expanded")
            r["sparks_container"].setVisible(not is_compact)
            if hasattr(r["spark_down"], "setFixedHeight"):
                r["spark_down"].setFixedHeight(26 if is_exp else 18)
                r["spark_up"].setFixedHeight(26 if is_exp else 18)

        sec.set_density = set_density
        return sec

    def _build_power_section(self) -> QWidget:
        sec = Section()
        sec.layout().setContentsMargins(9, 4, 9, 4)
        sec.layout().setSpacing(3)
        r = self._make_refs("power")

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        t = QLabel(tr("sec_power"))
        t.setStyleSheet("font-size:12px; font-weight:600;")
        hdr.addWidget(t)

        r["source_badge"] = QLabel("AC")
        r["source_badge"].setStyleSheet(
            f"color: {COLOR_GREEN}; background: rgba(110,217,138,25); "
            "border-radius: 4px; padding: 1px 5px; font-size: 9px; font-weight: 700; margin-left: 4px;"
        )
        hdr.addWidget(r["source_badge"])
        hdr.addStretch()

        r["state_label"] = QLabel("—")
        r["state_label"].setStyleSheet("color: rgba(255,255,255,160); font-size: 10px;")
        hdr.addWidget(r["state_label"])
        sec.layout().addLayout(hdr)

        power_row = QHBoxLayout()
        power_row.setContentsMargins(0, 2, 0, 0)
        power_row.setSpacing(8)

        r["watts_gauge"] = RadialGauge(min_val=0, max_val=45, unit="W", label="", color=COLOR_CYAN)
        r["watts_gauge"].setFixedSize(74, 62)
        power_row.addWidget(r["watts_gauge"])

        details_lay = QVBoxLayout()
        details_lay.setSpacing(2)
        details_lay.setContentsMargins(0, 0, 0, 0)

        r["watts_val"] = QLabel("— W")
        r["watts_val"].setStyleSheet(f"color: {COLOR_CYAN}; font-size: 15px; font-weight: 700;")
        details_lay.addWidget(r["watts_val"])

        r["wear_label"] = QLabel(f"{tr('battery_wear')}: —")
        r["wear_label"].setStyleSheet("color: rgba(255,255,255,160); font-size: 10px;")
        details_lay.addWidget(r["wear_label"])

        r["time_label"] = QLabel("—")
        r["time_label"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        details_lay.addWidget(r["time_label"])

        power_row.addLayout(details_lay, 1)
        sec.layout().addLayout(power_row)

        def set_density(size: str):
            is_compact = (size == "compact")
            r["watts_gauge"].setVisible(not is_compact)

        sec.set_density = set_density
        return sec

    def _build_cpu_cores_section(self) -> QWidget:
        sec = Section()
        sec.layout().setContentsMargins(9, 4, 9, 4)
        sec.layout().setSpacing(3)
        r = self._make_refs("cpu_cores")

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        t = QLabel(tr("sec_cpu_cores"))
        t.setStyleSheet("font-size:12px; font-weight:600;")
        hdr.addWidget(t)
        hdr.addStretch()

        r["cores_count"] = QLabel("— cores")
        r["cores_count"].setStyleSheet("color: rgba(255,255,255,160); font-size: 10px;")
        hdr.addWidget(r["cores_count"])
        sec.layout().addLayout(hdr)

        r["cores_container"] = QWidget()
        r["cores_grid"] = QGridLayout(r["cores_container"])
        r["cores_grid"].setContentsMargins(0, 2, 0, 0)
        r["cores_grid"].setSpacing(4)
        sec.layout().addWidget(r["cores_container"])
        r["core_chips"] = []

        def set_density(size: str):
            is_compact = (size == "compact")
            m = 0 if is_compact else 2
            r["cores_grid"].setContentsMargins(0, m, 0, 0)

        sec.set_density = set_density
        return sec

    def _build_quick_controls_section(self) -> QWidget:
        sec = Section()
        sec.layout().setContentsMargins(9, 4, 9, 4)
        sec.layout().setSpacing(3)
        r = self._make_refs("quick_controls")

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        t = QLabel(tr("sec_quick_controls"))
        t.setStyleSheet("font-size:11px; font-weight:600;")
        hdr.addWidget(t, 0)
        hdr.addStretch(1)

        p_th = _styles.THEME_PALETTES.get(self.settings.theme, _styles.DARK)
        r["turbo_btn"] = PaintedButton("⚡ Turbo")
        r["turbo_btn"]._padding_h = 6
        r["turbo_btn"]._font_px = 10
        r["turbo_btn"]._compute_size()
        r["turbo_btn"].setCheckable(True)
        r["turbo_btn"].setCursor(Qt.CursorShape.PointingHandCursor)
        r["turbo_btn"].setToolTip(tr("turbo_boost"))
        r["turbo_btn"].set_checked_appearance(
            p_th["preset_silent_bg"], p_th["preset_silent_border"], p_th["preset_silent_text"])
        r["turbo_btn"].clicked.connect(self._toggle_turbo)
        hdr.addWidget(r["turbo_btn"], 0)
        sec.layout().addLayout(hdr)

        bright_row = QHBoxLayout()
        bright_row.setContentsMargins(0, 3, 0, 0)
        bright_row.setSpacing(6)
        blbl = QLabel("☀")
        blbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,180);")
        bright_row.addWidget(blbl)

        r["bright_slider"] = QSlider(Qt.Orientation.Horizontal)
        r["bright_slider"].setRange(5, 100)
        r["bright_slider"].setValue(80)
        r["bright_slider"].sliderReleased.connect(self._on_brightness_released)
        bright_row.addWidget(r["bright_slider"], 1)

        r["bright_pct"] = QLabel("80%")
        r["bright_pct"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px; min-width: 28px;")
        bright_row.addWidget(r["bright_pct"])
        sec.layout().addLayout(bright_row)

        vol_row = QHBoxLayout()
        vol_row.setContentsMargins(0, 3, 0, 0)
        vol_row.setSpacing(6)
        vlbl = QLabel("🔊")
        vlbl.setStyleSheet("font-size: 12px; color: rgba(255,255,255,180);")
        vol_row.addWidget(vlbl)

        r["vol_slider"] = QSlider(Qt.Orientation.Horizontal)
        r["vol_slider"].setRange(0, 100)
        r["vol_slider"].setValue(50)
        r["vol_slider"].sliderReleased.connect(self._on_volume_released)
        vol_row.addWidget(r["vol_slider"], 1)

        r["vol_pct"] = QLabel("50%")
        r["vol_pct"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px; min-width: 28px;")
        vol_row.addWidget(r["vol_pct"])

        r["mute_btn"] = PaintedButton(tr("mute"))
        r["mute_btn"].setCheckable(True)
        r["mute_btn"].setCursor(Qt.CursorShape.PointingHandCursor)
        r["mute_btn"].setFixedWidth(46)
        r["mute_btn"].set_checked_appearance(
            p_th["preset_perf_bg"], p_th["preset_perf_border"], p_th["preset_perf_text"])
        r["mute_btn"].clicked.connect(self._toggle_mute)
        vol_row.addWidget(r["mute_btn"])
        sec.layout().addLayout(vol_row)

        def set_density(size: str):
            is_compact = (size == "compact")
            blbl.setVisible(not is_compact)
            r["bright_slider"].setVisible(not is_compact)
            r["bright_pct"].setVisible(not is_compact)

        sec.set_density = set_density
        return sec

    def _build_essentials_divider(self) -> QWidget:
        return EssentialsDividerWidget()

    def _toggle_turbo(self) -> None:
        r = self._refs.get("quick_controls", {})
        btn = r.get("turbo_btn")
        if not btn:
            return
        turn_on = btn.isChecked()
        ok, msg = sys_actions.set_turbo(turn_on)
        if not ok:
            self.log.warning(f"Failed to set turbo: {msg}")
            btn.setChecked(not turn_on)
        self._tick()

    def _on_brightness_released(self) -> None:
        r = self._refs.get("quick_controls", {})
        slider = r.get("bright_slider")
        if not slider:
            return
        val = slider.value()
        if "bright_pct" in r:
            r["bright_pct"].setText(f"{val}%")
        ok, msg = sys_actions.set_brightness(val)
        if not ok:
            self.log.warning(f"Failed to set brightness: {msg}")

    def _on_volume_released(self) -> None:
        r = self._refs.get("quick_controls", {})
        slider = r.get("vol_slider")
        if not slider:
            return
        val = slider.value()
        if "vol_pct" in r:
            r["vol_pct"].setText(f"{val}%")
        ok, msg = sys_actions.set_audio_volume(val)
        if not ok:
            self.log.warning(f"Failed to set volume: {msg}")

    def _toggle_mute(self) -> None:
        ok, msg = sys_actions.toggle_audio_mute()
        if not ok:
            self.log.warning(f"Failed to toggle mute: {msg}")
        self._tick()

    def _set_view_mode(self, mode: str) -> None:
        self.widgets.set_view_mode(mode)
        self._refresh_view_toggle()
        self.scroll_area.verticalScrollBar().setValue(0)
        self._update_min_height()
        if mode == "essentials":
            self.resize(WINDOW_FIXED_WIDTH, self.maximumHeight())
        QTimer.singleShot(0, self._update_min_height)

    def _refresh_view_toggle(self) -> None:
        if not hasattr(self, "btn_view_essentials"):
            return
        p_th = _styles.THEME_PALETTES.get(self.settings.theme, _styles.DARK)
        is_ess = (self.settings.view_mode == "essentials")
        self.btn_view_essentials.blockSignals(True)
        self.btn_view_all.blockSignals(True)
        self.btn_view_essentials.setChecked(is_ess)
        self.btn_view_all.setChecked(not is_ess)
        if is_ess:
            self.btn_view_essentials.set_checked_appearance(
                p_th["view_toggle_bg"], p_th["view_toggle_border"], p_th["view_toggle_text"]
            )
        else:
            self.btn_view_all.set_checked_appearance(
                p_th["view_toggle_bg"], p_th["view_toggle_border"], p_th["view_toggle_text"]
            )
        self.btn_view_essentials.blockSignals(False)
        self.btn_view_all.blockSignals(False)

    def _update_button_theme_appearances(self) -> None:
        """Update checked appearance colors of preset buttons, view mode toggles,
        and controls based on the active theme for WCAG AA contrast."""
        p_th = _styles.THEME_PALETTES.get(self.settings.theme, _styles.DARK)
        if hasattr(self, "_preset_buttons"):
            if "Silent" in self._preset_buttons:
                self._preset_buttons["Silent"].set_checked_appearance(
                    p_th["preset_silent_bg"], p_th["preset_silent_border"], p_th["preset_silent_text"]
                )
            if "Balanced" in self._preset_buttons:
                self._preset_buttons["Balanced"].set_checked_appearance(
                    p_th["preset_balanced_bg"], p_th["preset_balanced_border"], p_th["preset_balanced_text"]
                )
            if "Performance" in self._preset_buttons:
                self._preset_buttons["Performance"].set_checked_appearance(
                    p_th["preset_perf_bg"], p_th["preset_perf_border"], p_th["preset_perf_text"]
                )
        if hasattr(self, "btn_done_edit"):
            self.btn_done_edit.set_checked_appearance(
                p_th["preset_silent_bg"], p_th["preset_silent_border"], p_th["preset_silent_text"]
            )
        r_qc = self._refs.get("quick_controls", {})
        if "turbo_btn" in r_qc:
            r_qc["turbo_btn"].set_checked_appearance(
                p_th["preset_silent_bg"], p_th["preset_silent_border"], p_th["preset_silent_text"]
            )
        if "mute_btn" in r_qc:
            r_qc["mute_btn"].set_checked_appearance(
                p_th["preset_perf_bg"], p_th["preset_perf_border"], p_th["preset_perf_text"]
            )
        self._refresh_view_toggle()

    # ---------------------------------------------- edit / add widgets
    def _toggle_edit_mode(self) -> None:
        self.widgets.set_edit_mode(not self.widgets.is_edit_mode())

    def _on_edit_mode_changed(self, on: bool) -> None:
        self.edit_bar.setVisible(on)
        self.title_bar.set_edit_active(on)
        self.btn_edit_layout.setCheckable(True)
        p_th = _styles.THEME_PALETTES.get(self.settings.theme, _styles.DARK)
        self.btn_edit_layout.set_checked_appearance(
            p_th["view_toggle_bg"], p_th["view_toggle_border"], p_th["view_toggle_text"])
        self.btn_edit_layout.setChecked(on)
        self._reattach_refs()

    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if ev.key() == Qt.Key.Key_F11:
            self._toggle_fullscreen()
            ev.accept()
            return
        if ev.key() == Qt.Key.Key_Escape:
            if self.is_expanded_or_fs:
                self._exit_fullscreen()
                ev.accept()
                return
            if self.widgets.is_edit_mode():
                self._toggle_edit_mode()
                ev.accept()
                return
        super().keyPressEvent(ev)

    @property
    def is_expanded_or_fs(self) -> bool:
        return bool(self.isFullScreen() or self.isMaximized() or getattr(self, "_is_vert_maximized", False))

    def _reattach_refs(self) -> None:
        # Clear references for any widgets that are currently not in slots (e.g. hidden or below divider in essentials mode)
        for key in list(self._refs.keys()):
            if key not in self.widgets.slots:
                self._refs[key] = {}

        # The WidgetManager rebuilds widgets on order/visibility change.
        # Re-apply visual state that depends on widget references.
        self._apply_bg_overlay()
        self._update_button_theme_appearances()
        self._refresh_preset_visual_state()
        # Refresh manual UI state
        r = self._refs.get("fan", {})
        if self._manual_mode and "row" in r:
            r["row"].setVisible(True)
            r["toggle"].blockSignals(True)
            r["toggle"].setChecked(True)
            r["toggle"].setText(tr("deactivate"))
            r["toggle"].blockSignals(False)
            r["badge"].setText("ON")
            r["badge"].setStyleSheet(
                f"color: #1a1a22; background: {COLOR_ORANGE}; "
                "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
            )
        # Force an immediate tick to populate all values
        self._tick()
        # Recompute min height after the layout settles
        QTimer.singleShot(50, self._update_min_height)

    SNAP_THRESHOLD_PX = 14

    def _available_geometry(self) -> QRect:
        screen = self.screen() or QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 900, 900)

    def _content_stops(self) -> list[int]:
        """Actual card geometry plus chrome; no trailing inter-card spacing."""
        self.root.layout().activate()
        self.scroll_layout.activate()
        self.widget_container_layout.activate()
        margins = self.scroll_layout.contentsMargins()
        chrome = self.title_bar.height() + self.view_bar.height() + self.footer_bar.height()
        if not self.edit_bar.isHidden():
            chrome += self.edit_bar.height()
        base = chrome + margins.top() + margins.bottom()
        total = base
        stops = []
        for i in range(self.widget_container_layout.count()):
            slot = self.widget_container_layout.itemAt(i).widget()
            if slot is None or slot.isHidden():
                continue
            if stops:
                total += self.widget_container_layout.spacing()
            height = slot.heightForWidth(slot.width()) if slot.hasHeightForWidth() else slot.sizeHint().height()
            height = max(slot.minimumSizeHint().height(), height)
            slot.setFixedHeight(height)
            total += height
            stops.append(total)
        # An empty layout still has usable title, view selector and footer.
        return stops or [max(140, base)]

    def _compute_widget_stops(self) -> list[int]:
        limit = max(140, int(self._available_geometry().height() * 0.95))
        return sorted({min(height, limit) for height in self._content_stops()})

    def _update_min_height(self) -> None:
        if not self.isVisible():
            return
        self.setFixedWidth(WINDOW_FIXED_WIDTH)
        stops = self._compute_widget_stops()
        minimum, maximum = stops[0], stops[-1]
        # Remove previous constraints before applying potentially smaller bounds.
        self.setMinimumHeight(0)
        self.setMaximumHeight(maximum)
        self.setMinimumHeight(minimum)
        if self.is_expanded_or_fs:
            self.resize(WINDOW_FIXED_WIDTH, maximum)
        else:
            self.resize(WINDOW_FIXED_WIDTH, max(minimum, min(self.height(), maximum)))

    def _show_add_widget_menu(self) -> None:
        hidden = self.widgets.hidden_sections()
        if not hidden:
            title = tr("add_widget")
            msg = "All available widgets are already visible." if tr("save") == "Save" else "Tutti i widget disponibili sono già visibili."
            QMessageBox.information(self, title, msg)
            return
        menu = QMenu(self)
        for k in hidden:
            label = SECTION_LABELS.get(k, k)
            act = menu.addAction(f"+ {label}")
            act.triggered.connect(lambda _=False, key=k: self._add_widget(key))
        menu.exec(self.btn_add_widget.mapToGlobal(self.btn_add_widget.rect().bottomLeft()))

    def _add_widget(self, key: str) -> None:
        self.widgets.show_section(key)
        self._reattach_refs()
        QTimer.singleShot(50, self._update_min_height)

    # ----------------------------------------------- top processes (popup)
    def _open_top_processes(self) -> None:
        from .top_processes_dialog import TopProcessesDialog
        if getattr(self, "_top_procs_dialog", None) is None or not self._top_procs_dialog.isVisible():
            self._top_procs_dialog = TopProcessesDialog(self, count=10)
            self._top_procs_dialog.show()
        else:
            self._top_procs_dialog.raise_()
            self._top_procs_dialog.activateWindow()

    # ---------------------------------------------------- ticks
    def _tick(self) -> None:
        try:
            s = sensors.snapshot(include_top_processes=False)
        except Exception as e:
            self.log.error(f"snapshot error: {e}")
            self.stress.stop()
            if self.settings.manual_safety_enabled:
                indices = self._last_manual_fans | ({1} if self._manual_mode else set())
                for index in indices:
                    ok, message = mbpfan_ctrl.manual_off(index)
                    if not ok:
                        self.log.error(f"Snapshot failure auto restoration failed: {message}")
            return
        self._render(s)
        self.temp_updated.emit(s.cpu_temp_c)
        # Mini window mirrors temp+fan
        if self._mini is not None:
            fan_rpm = s.fans[0].rpm if s.fans else None
            self._mini.update_values(s.cpu_temp_c, fan_rpm)
        # Re-tint labels in case _render reset any to hardcoded white
        from .painted_frames import retint_labels
        retint_labels(self.root, self.settings.theme)

    def _tick_disk(self) -> None:
        if not self.settings.widget_visible.get("disk", False):
            return
        try:
            d = sensors.read_disk()
        except Exception as e:
            self.log.error(f"disk read error: {e}")
            return
        r = self._refs.get("disk", {})
        if not r:
            return
        if d is None:
            r["model"].setText(tr("disk_no_detected"))
            return
        model_txt = d.model or f"({tr('disk_unknown_model')})"
        r["model"].setText(f"{d.device} · {model_txt}")
        if d.temp_c is not None:
            color = _temp_color(d.temp_c, self.settings.theme)
            r["temp"].setText(f"{d.temp_c:.0f} °C")
            r["temp"].setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")
        else:
            r["temp"].setText("temp n/d")
            r["temp"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        sem = _styles.get_semantic_colors(self.settings.theme)
        if d.health == "OK":
            r["health"].setText("SMART · OK")
            r["health"].setStyleSheet(f"color: {sem['green']}; font-size: 10px; font-weight: 600;")
        elif d.health == "FAIL":
            r["health"].setText(tr("disk_smart_fail"))
            r["health"].setStyleSheet(f"color: {sem['red']}; font-size: 10px; font-weight: 700;")
        else:
            r["health"].setText(tr("disk_smart_na"))
            r["health"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        hours = f"{d.hours_on}" if d.hours_on is not None else "—"
        cycles = f"{d.power_cycles}" if d.power_cycles is not None else "—"
        if d.hours_on is not None:
            years = d.hours_on / 8760
            hours += f" ({years:.1f} {tr('disk_years')})"
        r["stats"].setText(f"◷ {hours} · ⟲ {cycles}")
        r["stats"].setToolTip(f"{tr('disk_hours')}: {hours} · {tr('disk_cycles')}: {cycles}")
        from .painted_frames import retint_labels
        retint_labels(self.root, self.settings.theme)

    # --------------------------------------------------------- render
    def _render(self, s: sensors.Snapshot) -> None:
        temp = s.cpu_temp_c
        if self.stress.running() and (temp is None or temp >= min(90, self.settings.manual_safety_temp_c)):
            self._stop_stress()
            self.log.warning("Stress workload stopped by thermal watchdog (temperature=%s)", temp)
            self._notify(tr("stress_safety_stopped"))
        temp_color_now = _temp_color(temp, self.settings.theme)

        # CPU
        r = self._refs.get("cpu", {})
        if r:
            if s.dmi and "device" in r:
                v = s.dmi.vendor.replace("Inc.", "").replace("COMPUTER INC.", "").strip()
                p = s.dmi.product.strip()
                dev_name = f"{v} {p}" if not p.lower().startswith(v.lower()) else p
                r["device"].setText(dev_name)
                backend_name = mbpfan_ctrl.get_backend_description()
                r["device"].setToolTip(f"{s.dmi.vendor} {s.dmi.product} ({s.dmi.chassis})\nBackend: {backend_name}")
            if temp is not None:
                r["temp"].setText(f"{temp:.1f}°")
                px = r["temp"].property("_temp_px") or self.TEMP_FONT_PX
                r["temp"].setStyleSheet(
                    f"color: {temp_color_now}; font-size: {px}px; "
                    "font-weight: 700; padding: 0px;"
                )
                r["spark"].add(temp)
                r["spark"].set_color(temp_color_now)
                self._hist_temp.append(temp)
            else:
                r["temp"].setText("—°")
            r["load"].setText(f"load {s.cpu_percent_total:.0f}%")
            if s.cpu_freq_mhz:
                mx = f" / {s.cpu_freq_max_mhz:.0f}" if s.cpu_freq_max_mhz else ""
                r["freq"].setText(f"{s.cpu_freq_mhz:.0f}{mx} MHz")
            else:
                r["freq"].setText("— MHz")
            if s.cpu_core_temps:
                if len(s.cpu_core_temps) <= 2:
                    r["cores"].setText("core: " + " ".join(f"{t:.0f}°" for t in s.cpu_core_temps))
                else:
                    min_c = min(s.cpu_core_temps)
                    max_c = max(s.cpu_core_temps)
                    r["cores"].setText(f"cores ({len(s.cpu_core_temps)}x): {min_c:.0f}°-{max_c:.0f}°")
            else:
                r["cores"].setText("core: —")
            self._refresh_governor_button()

        # Titlebar snowflake
        fan_rpm_now = s.fans[0].rpm if s.fans else 0
        self.title_bar.update_indicators(temp_color_now, fan_rpm_now)

        # Alert
        if temp is not None and self.settings.alert_enabled:
            if temp > self.settings.alert_temp_c and not self._notified_high_temp:
                self._notify(f"⚠ CPU {temp:.1f}°C > {self.settings.alert_temp_c}°C")
                self._notified_high_temp = True
                self.log.warning(f"High temp alert: {temp:.1f}°C")
            elif temp < self.settings.alert_temp_c - 5:
                self._notified_high_temp = False

        # Manual safety watchdog
        rf = self._refs.get("fan", {})
        manual_indices = {fan.index for fan in s.fans if fan.manual}
        if self._manual_mode:
            manual_indices.add(1)
        self._last_manual_fans = manual_indices
        if (manual_indices and self.settings.manual_safety_enabled
                and (temp is None or temp >= self.settings.manual_safety_temp_c)):
            errors = []
            for index in sorted(manual_indices):
                ok, error = mbpfan_ctrl.manual_off(index)
                if not ok:
                    errors.append(f"Fan {index}: {error}")
                else:
                    self._last_manual_fans.discard(index)
            if not errors:
                self._manual_mode = False
                self._manual_debounce.stop()
                self.manual_state_changed.emit(False)
                if "toggle" in rf:
                    rf["toggle"].blockSignals(True)
                    rf["toggle"].setChecked(False)
                    rf["toggle"].blockSignals(False)
                    rf["row"].hide()
                    rf["badge"].setText("OFF")
                    rf["toggle"].setText(tr("activate"))
                self._clear_active_preset()
                self._notify(tr("fan_safety_restored"))
            else:
                error = "; ".join(errors)
                self.log.error(f"Safety watchdog failed to restore auto: {error}")
                self._notify(tr("fan_auto_failed", error=error))

        # Fan
        if rf:
            if s.fans:
                fan = s.fans[0]
                rf["rpm"].setText(f"{fan.rpm} RPM")
                rf["bar"].setValue(int(fan.percent))
                tag = "  · MANUAL" if (fan.manual or self._manual_mode) else ""
                rf["minmax"].setText(f"{fan.label} · min {fan.min_rpm} / max {fan.max_rpm} RPM{tag}")
                rf["spark"].add(fan.rpm)
                rf["spark"].set_range(fan.min_rpm, fan.max_rpm)
                self._hist_fan.append(fan.rpm)

                if "multi_fans" in rf:
                    if len(s.fans) > 1:
                        details = " · ".join(f"{f.label}: {f.rpm} RPM" for f in s.fans)
                        rf["multi_fans"].setText(details)
                        rf["multi_fans"].setVisible(True)
                    else:
                        rf["multi_fans"].setVisible(False)
            else:
                rf["rpm"].setText("Auto")
                rf["bar"].setValue(0)
                rf["minmax"].setText(tr("fan_locked_tooltip"))
                if "multi_fans" in rf:
                    rf["multi_fans"].setVisible(False)

        # RAM
        rr = self._refs.get("ram", {})
        if rr and s.memory:
            m = s.memory
            rr["lbl"].setText(f"{sensors.format_bytes(m.used_bytes)} / {sensors.format_bytes(m.total_bytes)}")
            rr["bar"].setValue(int(m.percent))
            if m.swap_total_bytes:
                swap_txt = f"swap {sensors.format_bytes(m.swap_used_bytes)} ({m.swap_percent:.0f}%)"
            else:
                swap_txt = "swap —"
            rr["detail"].setText(
                f"{m.percent:.0f}% {tr('ram_used')} · {tr('ram_avail')} {sensors.format_bytes(m.available_bytes)} · {swap_txt}"
            )
            rr["spark"].add(m.percent)
            self._hist_ram.append(m.percent)
        elif rr:
            rr["lbl"].setText("—")
            rr["detail"].setText("—")
            rr["bar"].setValue(0)

        # GPU
        rg = self._refs.get("gpu", {})
        if rg and s.gpu:
            if s.gpu.cur_freq_mhz is not None:
                mx = f" / {s.gpu.max_freq_mhz}" if s.gpu.max_freq_mhz else ""
                rg["freq"].setText(f"{s.gpu.cur_freq_mhz}{mx} MHz")
            else:
                rg["freq"].setText("— MHz")
            gpu_temp = s.gpu_temp()
            if gpu_temp is not None:
                color = _temp_color(gpu_temp, self.settings.theme)
                rg["temp"].setText(f"{gpu_temp:.0f}°")
                rg["temp"].setStyleSheet(
                    f"color: {color}; font-size: 26px; font-weight: 700; padding: 0px;"
                )
            else:
                rg["temp"].setText("—°")
                rg["temp"].setStyleSheet(
                    "color: rgba(255,255,255,140); font-size: 26px; font-weight: 700; padding: 0px;"
                )
            # Update custom GPU card widget
            icon = rg.get("icon")
            if icon is not None:
                icon.set_state(s.gpu.busy_percent, gpu_temp)
        elif rg:
            rg["freq"].setText("— MHz")
            rg["temp"].setText("—°")
            if rg.get("icon"):
                rg["icon"].set_state(None, None)

        # Battery
        rb = self._refs.get("battery", {})
        if rb and s.battery:
            b = s.battery
            rb["pct"].setText(f"{b.percent:.0f} %")
            charging = tr("battery_charging") if b.plugged else tr("battery_discharging")
            time_left = ""
            if not b.plugged and b.seconds_left is not None:
                time_left = f" · {sensors.format_seconds(b.seconds_left)}"
            rb["status"].setText(f"{charging}{time_left}")
            sem = _styles.get_semantic_colors(self.settings.theme)
            if b.temp_c is not None:
                # Battery-specific colour bands (cooler than CPU)
                t = b.temp_c
                if t < 30:    bt_col = sem["green"]
                elif t < 40:  bt_col = sem["cyan"]
                elif t < 50:  bt_col = sem["orange"]
                else:         bt_col = sem["red"]
                rb["temp"].setText(f"{t:.1f} °C")
                rb["temp"].setStyleSheet(
                    f"color: {bt_col}; font-size: 10px; font-weight: 600;"
                )
            else:
                rb["temp"].setText("temp n/d")
                rb["temp"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
            # Update custom battery widget
            icon = rb.get("icon")
            if icon is not None:
                icon.set_state(b.percent, b.plugged)
            if b.health_percent is not None:
                h = b.health_percent
                if h >= 90:   hcol = sem["green"]
                elif h >= 70: hcol = sem["cyan"]
                elif h >= 50: hcol = sem["orange"]
                else:         hcol = sem["red"]
                rb["health"].setText(f"♥ {h:.0f}%")
                rb["health"].setToolTip(f"{tr('battery_health')}: {h:.0f}%")
                rb["health"].setStyleSheet(f"color: {hcol}; font-size: 10px; font-weight: 600;")
            else:
                rb["health"].setText("♥ —")
                rb["health"].setToolTip(tr('battery_health'))
                rb["health"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
            if b.cycle_count is not None:
                rb["cycles"].setText(f"⟲ {b.cycle_count}")
                rb["cycles"].setToolTip(f"{tr('battery_cycles')}: {b.cycle_count}")
            else:
                rb["cycles"].setText("⟲ —")
                rb["cycles"].setToolTip(tr('battery_cycles'))

        # Throttle
        rt = self._refs.get("throttle", {})
        if rt and s.throttle is not None:
            th = s.throttle
            sem = _styles.get_semantic_colors(self.settings.theme)
            if th.is_throttling or (th.last_seen_ago_s is not None and th.last_seen_ago_s < 30):
                rt["badge"].setText("THROTTLE!")
                rt["badge"].setStyleSheet(
                    f"color: white; background: {sem['red']}; "
                    "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
                )
                if th.is_throttling and not self._notified_throttle:
                    self._notify(tr("throttle_detected_notify"))
                    self._notified_throttle = True
                    self.log.warning("CPU thermal throttling detected")
            else:
                rt["badge"].setText("OK")
                rt["badge"].setStyleSheet(
                    f"color: {sem['green']}; background: rgba(110,217,138,30); "
                    "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
                )
                if th.last_seen_ago_s is None or th.last_seen_ago_s > 60:
                    self._notified_throttle = False
            pkg = th.package_throttle_count
            core = th.core_throttle_count
            rt["counts"].setText(f"package: {pkg if pkg is not None else '—'} · "
                                  f"core: {core if core is not None else '—'}")
            if th.last_seen_ago_s is None:
                rt["last"].setText(tr("throttle_no_events_boot"))
            else:
                secs = th.last_seen_ago_s
                if secs < 60:
                    when = tr("time_ago_s", s=int(secs))
                elif secs < 3600:
                    when = tr("time_ago_m", m=int(secs/60))
                else:
                    when = tr("time_ago_h", h=f"{secs/3600:.1f}")
                rt["last"].setText(tr("throttle_last_event", when=when))

        # Fan service controls (universal backends: thinkpad, asus_wmi, dell, applesmc, hwmon_pwm, mbpfan, firmware)
        if rf:
            backend = mbpfan_ctrl.get_backend()
            backend_desc = mbpfan_ctrl.get_backend_description()
            can_ctrl = mbpfan_ctrl.can_control_fan()

            sem = _styles.get_semantic_colors(self.settings.theme)
            if self._manual_mode:
                rf["status"].setText(tr("fan_manual_override"))
                rf["status"].setStyleSheet(f"color: {sem['orange']}; font-size: 10px; font-weight: 600;")
                if "btn_install" in rf: rf["btn_install"].setVisible(False)
                if "toggle" in rf: rf["toggle"].setEnabled(True)
                for b in self._preset_buttons.values(): b.setEnabled(False)
            elif backend == "mbpfan":
                status = mbpfan_ctrl.service_status()
                color = {"active": sem["green"], "failed": sem["red"],
                         "inactive": sem["orange"]}.get(status, sem["orange"])
                rf["status"].setText(f"mbpfan: {status}")
                rf["status"].setStyleSheet(f"color: {color}; font-size: 10px;")
                if "btn_install" in rf: rf["btn_install"].setVisible(status == "not-found")
                if "btn_restart" in rf: rf["btn_restart"].setEnabled(True)
                if "btn_tweaks" in rf: rf["btn_tweaks"].setEnabled(True)
                if "btn_curve" in rf: rf["btn_curve"].setEnabled(True)
                if "toggle" in rf: rf["toggle"].setEnabled(True)
                for b in self._preset_buttons.values(): b.setEnabled(True)
            elif backend in ("applesmc", "macsmc", "thinkpad", "asus_wmi", "dell", "hwmon_pwm"):
                rf["status"].setText(backend_desc)
                rf["status"].setStyleSheet(f"color: {sem['cyan']}; font-size: 10px; font-weight: 600;")
                if "btn_install" in rf: rf["btn_install"].setVisible(False)
                if "btn_restart" in rf: rf["btn_restart"].setEnabled(False)
                if "btn_tweaks" in rf: rf["btn_tweaks"].setEnabled(backend == "applesmc")
                if "btn_curve" in rf: rf["btn_curve"].setEnabled(backend == "applesmc")
                can_manual = backend in ("applesmc", "macsmc", "thinkpad", "hwmon_pwm")
                if "toggle" in rf: rf["toggle"].setEnabled(can_manual)
                for b in self._preset_buttons.values(): b.setEnabled(True)
            else:
                # Firmware / hardware auto (graceful read-only)
                rf["status"].setText(backend_desc)
                rf["status"].setStyleSheet(f"color: {sem['green']}; font-size: 10px;")
                if "btn_install" in rf: rf["btn_install"].setVisible(False)
                if "btn_restart" in rf: rf["btn_restart"].setEnabled(False)
                if "btn_tweaks" in rf: rf["btn_tweaks"].setEnabled(False)
                if "btn_curve" in rf: rf["btn_curve"].setEnabled(False)
                if "toggle" in rf:
                    rf["toggle"].setEnabled(False)
                    rf["toggle"].setToolTip(tr("fan_locked_tooltip"))
                for b in self._preset_buttons.values():
                    b.setEnabled(False)

        # Network
        rn = self._refs.get("network", {})
        if rn and s.network:
            net = s.network
            if "iface" in rn:
                rn["iface"].setText(net.interface or "down")
            if "down_rate" in rn:
                rn["down_rate"].setText(f"↓ {sensors.format_bytes(int(net.bytes_recv_per_sec))}/s")
            if "up_rate" in rn:
                rn["up_rate"].setText(f"↑ {sensors.format_bytes(int(net.bytes_sent_per_sec))}/s")
            if "spark_down" in rn:
                rn["spark_down"].add(net.bytes_recv_per_sec / 1024.0)
            if "spark_up" in rn:
                rn["spark_up"].add(net.bytes_sent_per_sec / 1024.0)
            if "wifi" in rn:
                if net.ssid:
                    sig_str = f" · {net.signal_percent}%" if net.signal_percent is not None else ""
                    raw = net.ssid
                    disp_ssid = (raw[:11] + "…") if len(raw) > 12 else raw
                    rn["wifi"].setText(f"📶 {disp_ssid}{sig_str}")
                    rn["wifi"].setToolTip(f"{raw}{sig_str}")
                else:
                    rn["wifi"].setText("")
                    rn["wifi"].setToolTip("")
            if "band" in rn:
                rn["band"].setText(net.band or "")

        # Power & Battery
        rp = self._refs.get("power", {})
        if rp and s.power:
            pw = s.power
            if "source_badge" in rp:
                rp["source_badge"].setText(pw.power_source)
                is_bat = (pw.power_source == "Battery")
                sem = _styles.get_semantic_colors(self.settings.theme)
                col = sem["orange"] if is_bat else sem["green"]
                bg = "rgba(255,180,84,30)" if is_bat else "rgba(110,217,138,25)"
                rp["source_badge"].setStyleSheet(
                    f"color: {col}; background: {bg}; border-radius: 4px; padding: 1px 5px; font-size: 9px; font-weight: 700; margin-left: 4px;"
                )
            if "watts_gauge" in rp and pw.watts is not None:
                rp["watts_gauge"].set_value(pw.watts)
            if "watts_val" in rp and pw.watts is not None:
                rp["watts_val"].setText(f"{pw.watts:.1f} W")
            if "wear_label" in rp:
                if pw.wear_percent is not None:
                    rp["wear_label"].setText(f"{tr('battery_wear')}: {pw.wear_percent:.1f}%")
                else:
                    rp["wear_label"].setText(f"{tr('battery_wear')}: —")
            if "state_label" in rp:
                if pw.is_charging:
                    rp["state_label"].setText(tr("battery_charging"))
                elif s.battery and s.battery.percent:
                    rp["state_label"].setText(f"{s.battery.percent:.0f}%")
            if "time_label" in rp:
                if pw.seconds_left:
                    rp["time_label"].setText(f"{sensors.format_seconds(pw.seconds_left)} remaining")
                elif pw.cycle_count:
                    rp["time_label"].setText(f"{pw.cycle_count} cycles")
                else:
                    rp["time_label"].setText("AC Connected")

        # CPU Cores Heatmap
        rc = self._refs.get("cpu_cores", {})
        if rc:
            temps = s.cpu_core_temps or ([s.cpu_temp_c] if s.cpu_temp_c else [])
            loads = s.cpu_percent_per_core or []
            if "cores_count" in rc:
                rc["cores_count"].setText(f"{len(temps)} cores")

            grid = rc.get("cores_grid")
            chips = rc.setdefault("core_chips", [])
            if grid is not None:
                COLS = 3
                while len(chips) < len(temps):
                    idx = len(chips)
                    chip = QLabel("")
                    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    chip.setMinimumHeight(22)
                    grid.addWidget(chip, idx // COLS, idx % COLS)
                    chips.append(chip)
                while len(chips) > len(temps):
                    chip = chips.pop()
                    grid.removeWidget(chip)
                    chip.deleteLater()

                for idx, t in enumerate(temps):
                    load_txt = f" · {loads[idx]:.0f}%" if idx < len(loads) else ""
                    chips[idx].setText(f"C{idx} {t:.0f}°{load_txt}")
                    col = _temp_color(t)
                    chips[idx].setStyleSheet(
                        f"color: {col}; background: rgba(255,255,255,10); "
                        f"border: 1px solid {col}40; border-radius: 5px; "
                        "font-size: 10px; font-weight: 600; padding: 2px 4px;"
                    )

        # Quick Controls
        rq = self._refs.get("quick_controls", {})
        if rq and s.quick_controls:
            qc = s.quick_controls
            if "bright_slider" in rq and qc.brightness_percent is not None:
                if not rq["bright_slider"].isSliderDown():
                    rq["bright_slider"].setValue(qc.brightness_percent)
                    rq["bright_pct"].setText(f"{qc.brightness_percent}%")
            if "turbo_btn" in rq and qc.turbo_enabled is not None:
                rq["turbo_btn"].blockSignals(True)
                rq["turbo_btn"].setChecked(qc.turbo_enabled)
                rq["turbo_btn"].setText("⚡ Turbo ON" if qc.turbo_enabled else "⚡ Turbo OFF")
                rq["turbo_btn"].blockSignals(False)
            if "vol_slider" in rq and qc.volume_percent is not None:
                if not rq["vol_slider"].isSliderDown():
                    rq["vol_slider"].setValue(qc.volume_percent)
                    rq["vol_pct"].setText(f"{qc.volume_percent}%")
            if "mute_btn" in rq:
                rq["mute_btn"].blockSignals(True)
                rq["mute_btn"].setChecked(qc.is_muted)
                rq["mute_btn"].setText("MUTED" if qc.is_muted else "Mute")
                rq["mute_btn"].blockSignals(False)

        new_alert_text = self._alert_btn_text()
        if self.btn_alert.text() != new_alert_text:
            self.btn_alert.setText(new_alert_text)

    # ------------------------------------------------- governor styling
    def _refresh_governor_button(self) -> None:
        profile = governor.current_profile()
        if profile == "Performance": color = COLOR_RED
        elif profile == "Saving": color = COLOR_GREEN
        else: color = COLOR_CYAN
        ref = self._refs.get("cpu", {}).get("gov")
        if ref is None: return
        if (ref.text() != profile or ref.property("_gov_color") != color):
            ref.setText(profile)
            ref.setProperty("_gov_color", color)
            # PaintedButton: use the "checked" appearance slot to colour the
            # border and text with the profile colour, and keep it permanently
            # checked so the appearance sticks.
            ref.set_checked_appearance("rgba(255,255,255,8)", color, color)
            ref.setCheckable(True)
            ref.setChecked(True)

    def _refresh_preset_visual_state(self) -> None:
        active = self.settings.active_preset
        for name, btn in self._preset_buttons.items():
            btn.blockSignals(True); btn.setChecked(name == active); btn.blockSignals(False)

    def _alert_btn_text(self) -> str:
        if self.settings.alert_enabled:
            return f"🔔 Alert > {self.settings.alert_temp_c}°C"
        return "🔔 Alert OFF"

    # ------------------------------------------------------ actions
    def _notify(self, msg: str) -> None:
        try:
            subprocess.Popen(
                ["notify-send", "-a", APP_NAME, "-u", "normal", APP_NAME, msg],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _apply_preset(self, name: str) -> None:
        if not mbpfan_ctrl.can_control_fan() and mbpfan_ctrl.get_backend() == "firmware":
            QMessageBox.information(self, tr("sec_fan"), tr("fan_locked_tooltip"))
            self._refresh_preset_visual_state(); return
        if self._manual_mode:
            msg = "Please disable manual override first." if tr("save") == "Save" else "Disattiva prima l'override manuale."
            QMessageBox.information(self, tr("fan_manual_override"), msg)
            self._refresh_preset_visual_state(); return
        import time as _t
        now = _t.monotonic()
        if hasattr(self, "_last_preset_t") and (now - self._last_preset_t) < 1.5:
            wait = 1.5 - (now - self._last_preset_t)
            self._notify(f"Wait {wait:.0f}s" if tr("save") == "Save" else f"Attendi {wait:.0f}s")
            self._refresh_preset_visual_state(); return
        self._last_preset_t = now
        for b in self._preset_buttons.values(): b.setEnabled(False)
        QTimer.singleShot(1600, self._unlock_presets)
        ok, msg = mbpfan_ctrl.apply_preset(name)
        if not ok:
            QMessageBox.critical(self, "Error", f"Preset {name} failed:\n{msg}")
            self._refresh_preset_visual_state()
        else:
            self._notify(tr("preset_applied", name=name))
            self.settings.active_preset = name
            config.save(self.settings)
            self._refresh_preset_visual_state()

    def _unlock_presets(self) -> None:
        if not self._manual_mode and mbpfan_ctrl.can_control_fan():
            for b in self._preset_buttons.values(): b.setEnabled(True)

    def _clear_active_preset(self) -> None:
        if self.settings.active_preset:
            self.settings.active_preset = ""
            config.save(self.settings)
            self._refresh_preset_visual_state()

    def _free_ram(self) -> None:
        rm = self._refs.get("maintenance", {})
        try:
            before = sensors.read_memory()
            ab = before.available_bytes if before else 0
        except Exception: ab = 0
        if "free_btn" in rm: rm["free_btn"].setEnabled(False)
        QApplication.processEvents()
        ok, msg = sys_actions.drop_caches()
        if "free_btn" in rm: rm["free_btn"].setEnabled(True)
        if not ok:
            QMessageBox.warning(self, tr("free_ram"), f"Operation failed:\n{msg}"); return
        try:
            after = sensors.read_memory()
            aa = after.available_bytes if after else 0
        except Exception: aa = 0
        freed = max(0, aa - ab)
        self._notify(tr("ram_freed", size=sensors.format_bytes(freed)) if freed > 0 else tr("cache_cleared"))

    # ---------------------------------------------------- manual override
    def _toggle_manual(self, on: bool) -> None:
        rf = self._refs.get("fan", {})
        if on:
            temp, _, _ = sensors.read_cpu_temps()
            if self.settings.manual_safety_enabled and (temp is None or temp >= self.settings.manual_safety_temp_c):
                self._notify(tr("fan_manual_unsafe"))
                rf["toggle"].blockSignals(True)
                rf["toggle"].setChecked(False)
                rf["toggle"].blockSignals(False)
                return
            reply = QMessageBox.warning(
                self, tr("manual_confirm_title"),
                tr("manual_confirm_msg", temp=self.settings.manual_safety_temp_c),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                rf["toggle"].blockSignals(True); rf["toggle"].setChecked(False); rf["toggle"].blockSignals(False)
                return
            fans = sensors.read_fans()
            cur = fans[0].rpm if fans else self._fan_min_rpm
            cur = max(self._fan_min_rpm, min(self._fan_max_rpm, cur))
            rf["slider"].blockSignals(True); rf["slider"].setValue(cur); rf["slider"].blockSignals(False)
            rf["rpm_lbl"].setText(f"{cur} RPM")
            ok, msg = mbpfan_ctrl.manual_on(cur)
            if not ok:
                QMessageBox.critical(self, "Error", f"Failed to activate manual override:\n{msg}")
                rf["toggle"].blockSignals(True); rf["toggle"].setChecked(False); rf["toggle"].blockSignals(False)
                return
            self._manual_mode = True
            rf["row"].setVisible(True)
            rf["toggle"].setText(tr("deactivate"))
            rf["badge"].setText("ON")
            rf["badge"].setStyleSheet(
                f"color: #1a1a22; background: {COLOR_ORANGE}; "
                "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
            )
            self._clear_active_preset()
            self.manual_state_changed.emit(True)
            self._notify(tr("manual_on_notify", rpm=cur))
        else:
            ok, msg = mbpfan_ctrl.manual_off()
            if not ok:
                self.log.error(f"Failed to restore automatic fan control: {msg}")
                rf["toggle"].blockSignals(True)
                rf["toggle"].setChecked(True)
                rf["toggle"].blockSignals(False)
                self._notify(tr("fan_auto_failed", error=msg))
                return
            self._manual_debounce.stop()
            self._manual_mode = False
            if "row" in rf: rf["row"].setVisible(False)
            rf["toggle"].setText(tr("activate"))
            rf["badge"].setText("OFF")
            rf["badge"].setStyleSheet(
                "color: rgba(255,255,255,140); background: rgba(255,255,255,12); "
                "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
            )
            self.manual_state_changed.emit(False)
            self._notify(tr("manual_off_notify"))

    def _on_slider_changed(self, value: int) -> None:
        rf = self._refs.get("fan", {})
        snapped = (value // 50) * 50
        if "rpm_lbl" in rf:
            rf["rpm_lbl"].setText(f"{snapped} RPM")
        if self._manual_mode:
            self._manual_debounce.start()

    def _apply_manual_rpm(self) -> None:
        if not self._manual_mode: return
        rf = self._refs.get("fan", {})
        if "slider" not in rf: return
        rpm = (rf["slider"].value() // 50) * 50
        ok, msg = mbpfan_ctrl.set_manual_rpm(rpm)
        if not ok:
            self.log.error(f"set_manual_rpm failed: {msg}")

    def is_manual_mode(self) -> bool:
        return self._manual_mode

    # ----------------------------- stress
    def _start_stress(self, duration: int) -> None:
        temp, _, _ = sensors.read_cpu_temps()
        if temp is None or temp >= min(90, self.settings.manual_safety_temp_c):
            QMessageBox.warning(self, tr("stress_title"), tr("stress_safety_stopped"))
            return
        if self.stress.running():
            QMessageBox.information(self, tr("stress_title"), tr("stress_already_running")); return
        if not (StressTest.has_stress_ng() or StressTest.has_stress()):
            reply = QMessageBox.question(
                self, tr("stress_title"),
                tr("stress_fallback_prompt"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes: return
        self.stress.start(duration)

    def _stop_stress(self) -> None:
        self.stress.stop()
        rs = self._refs.get("stress", {})
        if "status" in rs: rs["status"].setText(tr("stress_stopped"))
        if "btn_stop" in rs: rs["btn_stop"].setVisible(False)
        if "bar" in rs: rs["bar"].setVisible(False)
        for k in ("btn30", "btn60", "btn90"):
            if k in rs: rs[k].setEnabled(True)

    def _on_stress_started(self, duration: int) -> None:
        rs = self._refs.get("stress", {})
        if "status" in rs:
            rs["status"].setText(f"in corso · {self.stress.method()}")
            rs["status"].setStyleSheet(f"color: {COLOR_ORANGE}; font-size: 10px;")
        if "bar" in rs:
            rs["bar"].setRange(0, duration); rs["bar"].setValue(0); rs["bar"].setVisible(True)
        if "btn_stop" in rs: rs["btn_stop"].setVisible(True)
        for k in ("btn30", "btn60", "btn90"):
            if k in rs: rs[k].setEnabled(False)

    def _on_stress_progress(self, elapsed: int, total: int) -> None:
        rs = self._refs.get("stress", {})
        if "bar" in rs: rs["bar"].setValue(elapsed)
        if "status" in rs: rs["status"].setText(f"in corso · {elapsed}/{total}s")

    def _on_stress_finished(self, ok: bool, message: str) -> None:
        rs = self._refs.get("stress", {})
        if "status" in rs:
            rs["status"].setText("completato" if ok else "errore")
            rs["status"].setStyleSheet((f"color: {COLOR_GREEN};" if ok else f"color: {COLOR_RED};") + " font-size: 10px;")
        if "btn_stop" in rs: rs["btn_stop"].setVisible(False)
        if "bar" in rs: rs["bar"].setVisible(False)
        for k in ("btn30", "btn60", "btn90"):
            if k in rs: rs[k].setEnabled(True)
        self._notify(f"Stress test: {message}")

    # ----------------------------------------------------- dialogs
    def _open_tweaks(self) -> None:
        fans = sensors.read_fans()
        fmin = fans[0].min_rpm if fans else 1200
        fmax = fans[0].max_rpm if fans else 6500
        if TweaksDialog(self, fan_min=fmin, fan_max=fmax).exec():
            self._clear_active_preset()

    def _open_curve(self) -> None:
        fans = sensors.read_fans()
        fmin = fans[0].min_rpm if fans else 1200
        fmax = fans[0].max_rpm if fans else 6500
        if FanCurveDialog(self, fan_min=fmin, fan_max=fmax).exec():
            self._clear_active_preset()

    def _open_log(self) -> None:
        LogDialog(self).exec()

    def _open_preferences(self) -> None:
        dlg = PreferencesDialog(self.settings, self)
        dlg.exec()
        self.btn_alert.setText(self._alert_btn_text())
        if dlg.appearance_dirty():
            # Re-apply themed stylesheet globally
            from .styles import build_qss
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(build_qss(self.settings.theme,
                                             self.settings.fx_level,
                                             self.settings.bg_effect))
            # Matrix background overlay
            self._apply_bg_overlay()
            # Re-apply temp font in case it changed
            ref = self._refs.get("cpu", {}).get("temp")
            if ref is not None:
                self._apply_temp_font(ref)
        if dlg.restart_required():
            msg = "Display server change requires app restart." if tr("save") == "Save" else "Cambio server grafico richiede riavvio app."
            title = "Restart required" if tr("save") == "Save" else "Riavvio richiesto"
            QMessageBox.information(self, title, msg)

    def _open_cleanup(self) -> None:
        from .cleanup_dialog import CleanupDialog
        CleanupDialog(self).exec()

    def _restart_mbpfan(self) -> None:
        ok, msg = mbpfan_ctrl.restart_service()
        if ok:
            self._notify("mbpfan restarted" if tr("save") == "Save" else "mbpfan riavviato")
        else:
            err = "Error" if tr("save") == "Save" else "Errore"
            QMessageBox.critical(self, err, f"{msg}")

    def _install_mbpfan(self) -> None:
        title = "Install mbpfan?" if tr("save") == "Save" else "Installare mbpfan?"
        prompt = "Install and enable mbpfan service via pkexec?" if tr("save") == "Save" else "Installare e avviare il servizio mbpfan tramite pkexec?"
        reply = QMessageBox.question(self, title, prompt)
        if reply != QMessageBox.StandardButton.Yes: return
        ok, msg = mbpfan_ctrl.install_mbpfan()
        if ok:
            notify_txt = "mbpfan installed" if tr("save") == "Save" else "mbpfan installato"
            self._notify(notify_txt); mbpfan_ctrl.enable_service()
        else:
            err = "Error" if tr("save") == "Save" else "Errore"
            QMessageBox.critical(self, err, f"{msg}")

    def _show_governor_menu(self) -> None:
        avail = governor.available_governors()
        if not avail:
            QMessageBox.information(self, tr("sec_cpu"), tr("no_governor_avail")); return
        cur_profile = governor.current_profile()
        balanced_target = governor.resolve_balanced_governor()
        menu = QMenu(self)
        items = [
            ("Saving", "powersave", COLOR_GREEN),
            ("Balanced", balanced_target, COLOR_CYAN),
            ("Performance", "performance", COLOR_RED),
        ]
        for label, target, color in items:
            mark = "● " if label == cur_profile else "   "
            text = f"{mark}{label}"
            if target is None or target not in avail:
                text += f"  ({tr('not_available')})"
            act = menu.addAction(text)
            if target is None or target not in avail:
                act.setEnabled(False)
            else:
                act.triggered.connect(lambda _=False, p=label: self._set_profile(p))
        menu.addSeparator()
        info = menu.addAction(tr("real_governor", gov=governor.current_governor() or '—'))
        info.setEnabled(False)
        ref = self._refs.get("cpu", {}).get("gov")
        if ref is not None:
            pos = ref.mapToGlobal(ref.rect().bottomLeft())
        else:
            pos = QCursor.pos()
        menu.exec(pos)

    def _set_profile(self, profile: str) -> None:
        ok, msg = governor.set_profile(profile)
        if ok:
            self._notify(f"CPU: {profile}")
            self._refresh_governor_button()
        else:
            QMessageBox.warning(self, tr("sec_cpu"), f"Failed to apply governor:\n{msg}" if tr("save") == "Save" else f"Impossibile applicare:\n{msg}")

    # ----------------------------------------------- mini / widget / window
    def _apply_bg_overlay(self) -> None:
        """Update root frame (gradient/solid) + show/hide matrix overlay."""
        self.root.refresh()
        theme = self.settings.theme
        matrix_on = (self.settings.bg_effect == "matrix")
        # Propagate to title bar buttons (glyph color / hover bg)
        self.title_bar.set_theme(theme)
        # Propagate to all PaintedButtons so their fill+text follow the theme
        for btn in self.findChildren(PaintedButton):
            btn.set_theme(theme)
        for gauge in self.findChildren(RadialGauge):
            gauge.set_theme(theme)
        self._update_button_theme_appearances()
        for slot in self.widgets.slots.values():
            content = slot.content
            for child in content.findChildren(RoundedSection):
                child.set_theme(theme)
                child.set_matrix_mode(matrix_on)
            if isinstance(content, RoundedSection):
                content.set_theme(theme)
                content.set_matrix_mode(matrix_on)
        # Recolor every QLabel inside the content so any hardcoded white/grey
        # inline styles set during section building become readable on
        # light themes.
        self._retint_labels(theme)
        if matrix_on:
            self.matrix_bg.set_theme(theme)
            self.matrix_bg.setGeometry(0, 0, self.root.width(), self.root.height())
            self.matrix_bg.lower()
            self.matrix_bg.start()
        else:
            self.matrix_bg.stop()

    def _retint_labels(self, theme: str) -> None:
        from .painted_frames import retint_labels
        retint_labels(self.root, theme)

    def eventFilter(self, obj, ev):  # noqa: N802
        try:
            if obj is self.scroll_content and ev.type() == QEvent.Type.LayoutRequest:
                self._height_timer.start()
            if obj is self.root and ev.type() == ev.Type.Resize:
                self.matrix_bg.setGeometry(0, 0, self.root.width(), self.root.height())
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    def enter_mini_mode(self) -> None:
        if self._mini is not None: return
        self.hide()
        self._mini = MiniWindow()
        self._mini.closed.connect(self.exit_mini_mode)
        self._mini.expand_requested.connect(self.exit_mini_mode)
        if self.settings.mini_x >= 0:
            self._mini.move(self.settings.mini_x, self.settings.mini_y)
        else:
            screen = QGuiApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                self._mini.move(avail.right() - 190, avail.top() + 8)
        self._mini.show()
        self.settings.mini_mode = True
        config.save(self.settings)

    def exit_mini_mode(self) -> None:
        if self._mini is None: return
        # Save mini position
        self.settings.mini_x = self._mini.x()
        self.settings.mini_y = self._mini.y()
        self.settings.mini_mode = False
        config.save(self.settings)
        self._mini.close()
        self._mini = None
        self.show()
        self.activateWindow(); self.raise_()

    def _apply_window_flags(self, widget_mode: bool) -> None:
        flags = Qt.WindowType.FramelessWindowHint
        if widget_mode:
            flags |= Qt.WindowType.Tool
            flags |= Qt.WindowType.WindowStaysOnBottomHint
        else:
            flags |= Qt.WindowType.WindowMinimizeButtonHint
        self.setWindowFlags(flags)

    def enter_widget_mode(self) -> None:
        if self._widget_mode: return
        self._widget_mode = True
        self.settings.last_pos_x = self.x(); self.settings.last_pos_y = self.y()
        self._apply_window_flags(widget_mode=True)
        self.title_bar.set_widget_mode(True)
        self._place_widget_top_right()
        self.show()

    def exit_widget_mode(self) -> None:
        if not self._widget_mode: return
        self._widget_mode = False
        self._apply_window_flags(widget_mode=False)
        self.title_bar.set_widget_mode(False)
        if self.settings.last_pos_x >= 0 and self.settings.last_pos_y >= 0:
            self.move(self.settings.last_pos_x, self.settings.last_pos_y)
        self.show(); self.activateWindow(); self.raise_()

    def toggle_widget_mode(self) -> None:
        if self._widget_mode: self.exit_widget_mode()
        else: self.enter_widget_mode()
        self.settings.widget_pinned = self._widget_mode
        config.save(self.settings)
        self.widget_mode_changed.emit(self._widget_mode)

    def _place_widget_top_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None: return
        avail = screen.availableGeometry()
        w, h = self.width(), self.height()
        x = avail.right() - w - 12; y = avail.top() + 8
        if self.settings.widget_x >= 0:
            x = self.settings.widget_x; y = self.settings.widget_y
        self.move(x, y)

    def _restore_position(self) -> None:
        if self.settings.last_pos_x >= 0 and self.settings.last_pos_y >= 0:
            self.move(self.settings.last_pos_x, self.settings.last_pos_y)

    def _toggle_maximize(self) -> None:
        self._toggle_fullscreen()

    def _enter_fullscreen(self) -> None:
        if self._widget_mode:
            return
        if not hasattr(self, "_normal_geom_before_max") or not self._normal_geom_before_max:
            self._normal_geom_before_max = self.geometry()
        avail = self._available_geometry()
        self._is_vert_maximized = True
        self.setFixedWidth(WINDOW_FIXED_WIDTH)
        self.setWindowOpacity(1.0)
        if hasattr(self, "title_bar"):
            self.title_bar.btn_max.setText("❐")
            self.title_bar.setProperty("fullscreen", True)
            self.title_bar.style().unpolish(self.title_bar)
            self.title_bar.style().polish(self.title_bar)
        # Expand vertically from top to bottom of screen work area, strictly maintaining fixed width
        curr_x = self.x()
        max_x = avail.right() - WINDOW_FIXED_WIDTH
        new_x = max(avail.left(), min(curr_x, max_x))
        self.setGeometry(new_x, avail.top(), WINDOW_FIXED_WIDTH, avail.height())
        self._update_min_height()
        if hasattr(self, "root"):
            self.root.update()

    def _exit_fullscreen(self) -> None:
        self._is_vert_maximized = False
        self.setWindowOpacity(self.settings.clamped_opacity())
        if hasattr(self, "title_bar"):
            self.title_bar.btn_max.setText("□")
            self.title_bar.setProperty("fullscreen", False)
            self.title_bar.style().unpolish(self.title_bar)
            self.title_bar.style().polish(self.title_bar)
        self._update_min_height()
        if hasattr(self, "_normal_geom_before_max") and self._normal_geom_before_max:
            norm = self._normal_geom_before_max
            self.setGeometry(norm.x(), norm.y(), WINDOW_FIXED_WIDTH, norm.height())
        else:
            self.resize(WINDOW_FIXED_WIDTH, self.settings.window_h)
        if hasattr(self, "root"):
            self.root.update()

    def _toggle_fullscreen(self) -> None:
        if self.is_expanded_or_fs:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def changeEvent(self, ev: QEvent) -> None:  # noqa: N802
        if ev.type() == QEvent.Type.WindowStateChange:
            if self.isFullScreen() or self.isMaximized():
                # Avoid native window manager widening the window; keep it strictly fixed width
                QTimer.singleShot(0, self._enforce_vert_maximize_from_wm)
        super().changeEvent(ev)

    def _enforce_vert_maximize_from_wm(self) -> None:
        if self.isFullScreen() or self.isMaximized():
            self.showNormal()
            self._enter_fullscreen()

    # ------------------------------------------------------ events
    def wheelEvent(self, ev: QWheelEvent) -> None:  # noqa: N802
        # Forward scroll events directly to the vertical scroll area so the page scrolls
        # strictly vertically, ignoring any lateral/horizontal deltas
        if hasattr(self, "scroll_area") and self.scroll_area:
            self.scroll_area.wheelEvent(ev)
        else:
            super().wheelEvent(ev)

    def contextMenuEvent(self, ev: QContextMenuEvent) -> None:  # noqa: N802
        menu = QMenu(self)
        is_fs = self.is_expanded_or_fs
        fs_label = tr("exit_fullscreen") if is_fs else tr("fullscreen")
        menu.addAction(f"⛶ {fs_label} (F11)").triggered.connect(self._toggle_fullscreen)
        menu.addSeparator()
        op_menu = menu.addMenu(tr("transparency"))
        for label, val in (("30%", 0.30), ("50%", 0.50), ("75%", 0.75), ("100%", 1.00)):
            act = op_menu.addAction(label); act.setCheckable(True)
            act.setChecked(abs(self.windowOpacity() - val) < 0.025)
            act.triggered.connect(lambda _=False, v=val: self._set_opacity(v))
        menu.addSeparator()
        pin_label = tr("unpin_from_desktop") if self._widget_mode else tr("pin_to_desktop")
        menu.addAction(pin_label).triggered.connect(self.toggle_widget_mode)
        menu.addAction(tr("mini_mode")).triggered.connect(self.enter_mini_mode)
        menu.addSeparator()
        menu.addAction(f"🔧 {tr('edit_widgets')}").triggered.connect(self._toggle_edit_mode)
        menu.addAction(f"⚙ {tr('preferences')}…").triggered.connect(self._open_preferences)
        menu.addSeparator()
        menu.addAction(tr("quit_app")).triggered.connect(self.quit_requested.emit)
        menu.exec(ev.globalPos())

    def _set_opacity(self, value: float) -> None:
        self.setWindowOpacity(value); self.settings.opacity = value
        config.save(self.settings)

    def closeEvent(self, ev) -> None:  # noqa: N802
        ev.ignore(); self.hide()

    def moveEvent(self, ev) -> None:  # noqa: N802
        super().moveEvent(ev)
        if self._widget_mode:
            self.settings.widget_x = self.x(); self.settings.widget_y = self.y()
        else:
            self.settings.last_pos_x = self.x(); self.settings.last_pos_y = self.y()

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self.settings.window_w = WINDOW_FIXED_WIDTH
        if not self.is_expanded_or_fs and not self._widget_mode:
            self.settings.window_h = self.height()

    def _edge_at(self, pos: QPoint) -> Optional[str]:
        if self._widget_mode or self.is_expanded_or_fs:
            return None
        m = RESIZE_MARGIN
        w, h = self.width(), self.height()
        # Strictly lock horizontal edges and corners: sides can never be grabbed or resized
        if pos.x() <= m or pos.x() >= w - m:
            return None
        top = pos.y() <= m
        bottom = pos.y() >= h - m
        if top:
            return "t"
        if bottom:
            return "b"
        return None

    def _cursor_for_edge(self, edge: Optional[str]) -> Qt.CursorShape:
        if edge in ("t", "b"):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if self._resize_edge and ev.buttons() & Qt.MouseButton.LeftButton:
            self._do_resize(ev.globalPosition().toPoint()); ev.accept(); return
        edge = self._edge_at(ev.position().toPoint())
        self.setCursor(self._cursor_for_edge(edge))

    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if ev.button() != Qt.MouseButton.LeftButton: return
        edge = self._edge_at(ev.position().toPoint())
        if edge:
            self._resize_edge = edge
            self._resize_start_geom = self.geometry()
            self._resize_start_mouse = ev.globalPosition().toPoint()
            ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        self._resize_edge = None

    def _do_resize(self, global_pos: QPoint) -> None:
        if not self._resize_start_geom or not self._resize_start_mouse:
            return
        dy = global_pos.y() - self._resize_start_mouse.y()
        g = QRect(self._resize_start_geom)

        stops = self._compute_widget_stops()
        min_h, max_h = stops[0], stops[-1]

        edge = self._resize_edge or ""
        if edge == "b":
            desired_h = self._resize_start_geom.height() + dy
            # Magnetic trigger stops at each widget card end
            nearest = min(stops, key=lambda stop: abs(desired_h - stop))
            if abs(desired_h - nearest) <= self.SNAP_THRESHOLD_PX:
                desired_h = nearest
            # Strictly limit to where widgets end (fino a dove finiscono i widget)
            final_h = max(min_h, min(desired_h, max_h))
            g.setHeight(final_h)
        elif edge == "t":
            desired_h = self._resize_start_geom.height() - dy
            nearest = min(stops, key=lambda stop: abs(desired_h - stop))
            if abs(desired_h - nearest) <= self.SNAP_THRESHOLD_PX:
                desired_h = nearest
            final_h = max(min_h, min(desired_h, max_h))
            g.setTop(g.bottom() - final_h + 1)

        # Strictly lock width horizontally to WINDOW_FIXED_WIDTH
        g.setWidth(WINDOW_FIXED_WIDTH)
        self.setGeometry(g)
