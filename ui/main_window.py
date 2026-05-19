"""
Fresh Fan Manager — main monitoring window.
Frameless, translucent, with reorderable widget sections.
"""
from __future__ import annotations

import subprocess
from collections import deque
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPoint, QRect, Signal
from PySide6.QtGui import (QCursor, QMouseEvent, QWheelEvent, QFont,
                            QGuiApplication, QContextMenuEvent)
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QFrame, QPushButton, QProgressBar,
                                QSizePolicy, QGridLayout, QMenu, QMessageBox,
                                QSlider)

from core import sensors, mbpfan_ctrl, governor, config, sys_actions
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
from .widget_manager import WidgetManager, SECTION_LABELS
from .mini_window import MiniWindow
from .matrix_bg import MatrixBackground

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


def _temp_color(temp: Optional[float]) -> str:
    if temp is None:
        return COLOR_CYAN
    if temp < 50:
        return COLOR_GREEN
    if temp < 65:
        return COLOR_CYAN
    if temp < 78:
        return COLOR_ORANGE
    if temp < 90:
        return COLOR_RED_ORANGE
    return COLOR_RED


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
        self._notified_high_temp = False
        self._notified_throttle = False
        self._drag_pos: Optional[QPoint] = None
        self._resize_edge: Optional[str] = None
        self._resize_start_geom: Optional[QRect] = None
        self._resize_start_mouse: Optional[QPoint] = None
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
        self._apply_window_flags(widget_mode=False)
        self.setMinimumSize(280, 420)
        self.resize(settings.window_w, settings.window_h)
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
        info = QLabel("Modalità modifica — trascina ⋮⋮ per spostare, ✕ per nascondere")
        info.setStyleSheet("color: rgba(255,255,255,180); font-size: 10px;")
        edit_lay.addWidget(info)
        edit_lay.addStretch()
        self.btn_add_widget = PaintedButton("+ Aggiungi")
        self.btn_add_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_widget.clicked.connect(self._show_add_widget_menu)
        edit_lay.addWidget(self.btn_add_widget)
        self.btn_done_edit = PaintedButton("✓ Fine")
        self.btn_done_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_done_edit.clicked.connect(self._toggle_edit_mode)
        edit_lay.addWidget(self.btn_done_edit)
        self.edit_bar.setVisible(False)
        self.edit_bar.setStyleSheet(
            "QFrame#editBar { background: rgba(127,215,255,18); "
            "border-bottom: 1px solid rgba(127,215,255,60); }"
        )
        root_layout.addWidget(self.edit_bar)

        # Content (window grows freely to fit; no internal scroll)
        content = QWidget()
        content.setObjectName("scrollContent")
        content.setMouseTracking(True)
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        clayout = QVBoxLayout(content)
        clayout.setContentsMargins(8, 6, 8, 6)
        clayout.setSpacing(5)
        root_layout.addWidget(content, 1)

        # Widget container — holds all reorderable sections
        self.widget_container_layout = QVBoxLayout()
        self.widget_container_layout.setSpacing(5)
        self.widget_container_layout.setContentsMargins(0, 0, 0, 0)
        clayout.addLayout(self.widget_container_layout)

        # Hook up the widget manager with section builders
        builders = {
            "cpu":         self._build_cpu_section,
            "fan":         self._build_fan_section,
            "maintenance": self._build_maintenance_section,
            "ram":         self._build_ram_section,
            "gpu_battery": self._build_gpu_battery_section,
            "throttle":    self._build_throttle_section,
            "disk":        self._build_disk_section,
            "stress":      self._build_stress_section,
        }
        self.widgets = WidgetManager(self.settings,
                                     self.widget_container_layout,
                                     builders)
        self.widgets.layout_changed.connect(self._reattach_refs)

        # Footer: alert (sx) — preferenze — log — modifica layout (dx)
        foot = QHBoxLayout()
        foot.setSpacing(4)
        foot.setContentsMargins(0, 0, 0, 0)
        self.btn_alert = PaintedButton(self._alert_btn_text())
        self.btn_alert.setToolTip("Soglia di allerta temperatura")
        self.btn_alert.clicked.connect(self._open_preferences)
        foot.addWidget(self.btn_alert)
        foot.addStretch()
        self.btn_prefs = PaintedButton("⚙ Preferenze")
        self.btn_prefs.clicked.connect(self._open_preferences)
        foot.addWidget(self.btn_prefs)
        self.btn_show_log = PaintedButton("Log")
        self.btn_show_log.clicked.connect(self._open_log)
        foot.addWidget(self.btn_show_log)
        self.btn_edit_layout = PaintedButton("🔧")
        self.btn_edit_layout.setToolTip("Modifica layout dei widget")
        self.btn_edit_layout.setFixedWidth(34)
        self.btn_edit_layout.clicked.connect(self._toggle_edit_mode)
        foot.addWidget(self.btn_edit_layout)
        clayout.addLayout(foot)

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
        r["indicator"].setToolTip("Apri Top processi in finestra separata")
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
        r["gov"].setCursor(Qt.CursorShape.PointingHandCursor)
        r["gov"].setToolTip("Cambia profilo CPU")
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
        f_h = QLabel("Ventola"); f_h.setStyleSheet("font-size:13px; font-weight:600;")
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

        # ----- Integrated profile presets (formerly mbpfan section) -----
        preset_row = QHBoxLayout(); preset_row.setSpacing(4)
        preset_row.setContentsMargins(0, 6, 0, 0)
        r["btn_silent"] = PaintedButton("Silent")
        r["btn_balanced"] = PaintedButton("Balanced")
        r["btn_perf"] = PaintedButton("Perform.")
        r["btn_silent"].set_checked_appearance(
            "rgba(110, 217, 138, 50)", "#6ed98a", "#2c8a44")
        r["btn_balanced"].set_checked_appearance(
            "rgba(127, 215, 255, 50)", "#7FD7FF", "#1f6c8c")
        r["btn_perf"].set_checked_appearance(
            "rgba(255, 94, 87, 50)", "#ff5e57", "#b03038")
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
        r["btn_curve"] = PaintedButton("Curva…"); r["btn_curve"].clicked.connect(self._open_curve)
        r["btn_tweaks"] = PaintedButton("Tweak…"); r["btn_tweaks"].clicked.connect(self._open_tweaks)
        r["btn_restart"] = PaintedButton("Riavvia"); r["btn_restart"].clicked.connect(self._restart_mbpfan)
        r["btn_install"] = PaintedButton("Installa servizio")
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
        ml = QLabel("Override manuale RPM")
        ml.setStyleSheet("color: rgba(255,255,255,200); font-size: 11px; font-weight: 600;")
        manual_header.addWidget(ml); manual_header.addStretch()
        r["badge"] = QLabel("OFF")
        r["badge"].setStyleSheet(
            "color: rgba(255,255,255,140); background: rgba(255,255,255,12); "
            "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
        )
        manual_header.addWidget(r["badge"])
        r["toggle"] = PaintedButton("Attiva")
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
        r["detail"] = QLabel("usata — · disp. — · swap —")
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
        h = QLabel("Pulizia & manutenzione")
        h.setStyleSheet("font-size:13px; font-weight:600;")
        sec.layout().addWidget(h)
        info = QLabel("Libera cache di sistema o esegui una pulizia approfondita.")
        info.setStyleSheet("color: rgba(255,255,255,150); font-size: 10px;")
        info.setWordWrap(True)
        sec.layout().addWidget(info)
        row = QHBoxLayout(); row.setSpacing(6)
        r["free_btn"] = PaintedButton("🧹 Libera RAM")
        r["free_btn"].setToolTip(
            "Esegue 'sync' + drop_caches=3 — libera cache pagina, dentries e "
            "inodes. Non tocca la memoria usata dai processi."
        )
        r["free_btn"].setCursor(Qt.CursorShape.PointingHandCursor)
        r["free_btn"].clicked.connect(self._free_ram)
        row.addWidget(r["free_btn"], 1)
        r["cleanup_btn"] = PaintedButton("🧽 Cleanup avanzato…")
        r["cleanup_btn"].setToolTip(
            "Pulizia di log di sistema, cache pacchetti apt, cache utente, "
            "thumbnail, cestino. Permette selezione voce per voce."
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
        bh = QLabel("Batteria"); bh.setStyleSheet("font-size: 13px; font-weight: 600;")
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
        det2 = QHBoxLayout(); det2.setSpacing(6); det2.setContentsMargins(0, 0, 0, 0)
        rb["health"] = QLabel("salute —")
        rb["health"].setProperty("_skip_retint", True)
        rb["health"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        rb["cycles"] = QLabel("cicli —")
        rb["cycles"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        det2.addWidget(rb["health"]); det2.addStretch(); det2.addWidget(rb["cycles"])
        bat_sec.layout().addLayout(det2)
        hl.addWidget(bat_sec, 1)
        return wrap

    def _build_throttle_section(self) -> QWidget:
        sec = Section()
        r = self._make_refs("throttle")
        title = QHBoxLayout()
        h = QLabel("⚡ Throttling")
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
        r["last"] = QLabel("Nessun evento recente")
        r["last"].setStyleSheet("color: rgba(255,255,255,130); font-size: 10px;")
        sec.layout().addWidget(r["last"])
        return sec

    def _build_disk_section(self) -> QWidget:
        sec = Section()
        r = self._make_refs("disk")
        h = QLabel("💾 Disco")
        h.setStyleSheet("font-size:13px; font-weight:600;")
        sec.layout().addWidget(h)
        r["model"] = QLabel("rilevamento…")
        r["model"].setStyleSheet("color: rgba(255,255,255,170); font-size: 11px;")
        sec.layout().addWidget(r["model"])
        r["temp"] = QLabel("temp —")
        r["temp"].setProperty("_skip_retint", True)
        r["temp"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        sec.layout().addWidget(r["temp"])
        r["health"] = QLabel("SMART —")
        r["health"].setProperty("_skip_retint", True)
        r["health"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        sec.layout().addWidget(r["health"])
        r["stats"] = QLabel("ore — · cicli —")
        r["stats"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        sec.layout().addWidget(r["stats"])
        return sec

    def _build_stress_section(self) -> QWidget:
        sec = Section()
        # Tighter padding only — content is fully preserved
        sec.layout().setContentsMargins(9, 4, 9, 4)
        sec.layout().setSpacing(3)
        r = self._make_refs("stress")
        title = QHBoxLayout(); title.setSpacing(6)
        h = QLabel("Stress test"); h.setStyleSheet("font-size:13px; font-weight:600;")
        title.addWidget(h); title.addStretch()
        r["status"] = QLabel("inattivo")
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

    # ---------------------------------------------- edit / add widgets
    def _toggle_edit_mode(self) -> None:
        on = not self.widgets.is_edit_mode()
        self.widgets.set_edit_mode(on)
        self.edit_bar.setVisible(on)
        self.title_bar.set_edit_active(on)
        # Visual feedback on the footer button via PaintedButton's checked state
        self.btn_edit_layout.setCheckable(True)
        self.btn_edit_layout.set_checked_appearance(
            "rgba(127,215,255,40)", COLOR_CYAN, COLOR_CYAN)
        self.btn_edit_layout.setChecked(on)
        self._reattach_refs()

    def _reattach_refs(self) -> None:
        # The WidgetManager rebuilds widgets on order/visibility change.
        # _refs are populated only at build time; on rebuild they're refreshed
        # automatically because each builder repopulates self._refs[key].
        # Re-apply visual state that depends on widget references.
        self._refresh_preset_visual_state()
        # Refresh manual UI state
        r = self._refs.get("fan", {})
        if self._manual_mode and "row" in r:
            r["row"].setVisible(True)
            r["toggle"].blockSignals(True)
            r["toggle"].setChecked(True)
            r["toggle"].setText("Disattiva")
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

    def _update_min_height(self) -> None:
        """Lock the minimum window size (both axes) to the current content's
        preferred size. Lets the user enlarge the window freely but prevents
        shrinking it small enough to squash widgets or overlap the footer
        buttons horizontally."""
        if not self.isVisible():
            return
        try:
            hint = self.root.layout().totalSizeHint()
            content_h = hint.height()
            content_w = hint.width()
        except Exception:
            content_h = self.root.sizeHint().height()
            content_w = self.root.sizeHint().width()
        new_min_h = max(420, content_h + 4)
        # Width: use the footer row's sizeHint as the hard lower bound so the
        # bottom buttons never overlap each other. Margins: outer 8+8 + 3
        # gaps × default layout spacing (~6) = ~32. Keep tight so the user
        # can shrink until buttons almost touch.
        try:
            foot_w = (self.btn_alert.sizeHint().width()
                       + self.btn_prefs.sizeHint().width()
                       + self.btn_show_log.sizeHint().width()
                       + self.btn_edit_layout.sizeHint().width()
                       + 24)  # 8+8 content margins + small inter-button slack
        except Exception:
            foot_w = 0
        new_min_w = max(280, foot_w)
        if new_min_h != self.minimumHeight():
            self.setMinimumHeight(new_min_h)
            if self.height() < new_min_h:
                self.resize(self.width(), new_min_h)
        if new_min_w != self.minimumWidth():
            self.setMinimumWidth(new_min_w)
            if self.width() < new_min_w:
                self.resize(new_min_w, self.height())

    def _show_add_widget_menu(self) -> None:
        hidden = self.widgets.hidden_sections()
        if not hidden:
            QMessageBox.information(self, "Aggiungi widget",
                                    "Tutti i widget disponibili sono già visibili.")
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
            r["model"].setText("Nessun disco rilevato")
            return
        model_txt = d.model or "(modello sconosciuto)"
        r["model"].setText(f"{d.device} · {model_txt}")
        if d.temp_c is not None:
            color = _temp_color(d.temp_c)
            r["temp"].setText(f"temp {d.temp_c:.0f} °C")
            r["temp"].setStyleSheet(f"color: {color}; font-size: 10px;")
        else:
            r["temp"].setText("temp n/d (richiede smartmontools)")
            r["temp"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        if d.health == "OK":
            r["health"].setText("SMART · OK")
            r["health"].setStyleSheet(f"color: {COLOR_GREEN}; font-size: 10px;")
        elif d.health == "FAIL":
            r["health"].setText("SMART · GUASTO IMMINENTE")
            r["health"].setStyleSheet(f"color: {COLOR_RED}; font-size: 10px; font-weight: 700;")
        else:
            r["health"].setText("SMART n/d")
            r["health"].setStyleSheet("color: rgba(255,255,255,140); font-size: 10px;")
        hours = f"{d.hours_on}" if d.hours_on is not None else "—"
        cycles = f"{d.power_cycles}" if d.power_cycles is not None else "—"
        if d.hours_on is not None:
            years = d.hours_on / 8760
            hours += f" ({years:.1f} anni)"
        r["stats"].setText(f"ore {hours} · cicli {cycles}")
        from .painted_frames import retint_labels
        retint_labels(self.root, self.settings.theme)

    # --------------------------------------------------------- render
    def _render(self, s: sensors.Snapshot) -> None:
        temp = s.cpu_temp_c
        temp_color_now = _temp_color(temp)

        # CPU
        r = self._refs.get("cpu", {})
        if r:
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
            r["load"].setText(f"load {s.cpu_percent_total:.0f}%")
            if s.cpu_freq_mhz:
                mx = f" / {s.cpu_freq_max_mhz:.0f}" if s.cpu_freq_max_mhz else ""
                r["freq"].setText(f"{s.cpu_freq_mhz:.0f}{mx} MHz")
            if s.cpu_core_temps:
                r["cores"].setText("core: " + " ".join(f"{t:.0f}°" for t in s.cpu_core_temps))
            self._refresh_governor_button()

        # Titlebar snowflake
        fan_rpm_now = s.fans[0].rpm if s.fans else 0
        self.title_bar.update_indicators(temp_color_now, fan_rpm_now)

        # Alert
        if temp is not None and self.settings.alert_enabled:
            if temp > self.settings.alert_temp_c and not self._notified_high_temp:
                self._notify(f"⚠ CPU {temp:.1f}°C oltre soglia ({self.settings.alert_temp_c}°C)")
                self._notified_high_temp = True
                self.log.warning(f"High temp alert: {temp:.1f}°C")
            elif temp < self.settings.alert_temp_c - 5:
                self._notified_high_temp = False

        # Manual safety watchdog
        rf = self._refs.get("fan", {})
        if (self._manual_mode and self.settings.manual_safety_enabled
                and temp is not None and temp > self.settings.manual_safety_temp_c
                and "toggle" in rf):
            self.log.warning(
                f"Safety watchdog: {temp:.1f}°C > {self.settings.manual_safety_temp_c}°C — manual OFF"
            )
            self._notify(f"🛡 Sicurezza: {temp:.0f}°C, sblocco ventola")
            rf["toggle"].setChecked(False)

        # Fan
        if rf and s.fans:
            fan = s.fans[0]
            rf["rpm"].setText(f"{fan.rpm} RPM")
            rf["bar"].setValue(int(fan.percent))
            tag = "  · MANUAL" if (fan.manual or self._manual_mode) else ""
            rf["minmax"].setText(f"{fan.label} · min {fan.min_rpm} / max {fan.max_rpm} RPM{tag}")
            rf["spark"].add(fan.rpm)
            rf["spark"].set_range(fan.min_rpm, fan.max_rpm)
            self._hist_fan.append(fan.rpm)

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
                f"{m.percent:.0f}% usata · disp. {sensors.format_bytes(m.available_bytes)} · {swap_txt}"
            )
            rr["spark"].add(m.percent)
            self._hist_ram.append(m.percent)

        # GPU
        rg = self._refs.get("gpu", {})
        if rg and s.gpu:
            if s.gpu.cur_freq_mhz is not None:
                mx = f" / {s.gpu.max_freq_mhz}" if s.gpu.max_freq_mhz else ""
                rg["freq"].setText(f"{s.gpu.cur_freq_mhz}{mx} MHz")
            gpu_temp = s.gpu_temp()
            if gpu_temp is not None:
                color = _temp_color(gpu_temp)
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

        # Battery
        rb = self._refs.get("battery", {})
        if rb and s.battery:
            b = s.battery
            rb["pct"].setText(f"{b.percent:.0f} %")
            charging = "in carica" if b.plugged else "in scarica"
            time_left = ""
            if not b.plugged and b.seconds_left is not None:
                time_left = f" · {sensors.format_seconds(b.seconds_left)}"
            rb["status"].setText(f"{charging}{time_left}")
            if b.temp_c is not None:
                # Battery-specific colour bands (cooler than CPU)
                t = b.temp_c
                if t < 30:    bt_col = COLOR_GREEN
                elif t < 40:  bt_col = COLOR_CYAN
                elif t < 50:  bt_col = COLOR_ORANGE
                else:         bt_col = COLOR_RED
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
                if h >= 90:   hcol = COLOR_GREEN
                elif h >= 70: hcol = COLOR_CYAN
                elif h >= 50: hcol = COLOR_ORANGE
                else:         hcol = COLOR_RED
                rb["health"].setText(f"salute {h:.0f}%")
                rb["health"].setStyleSheet(f"color: {hcol}; font-size: 10px; font-weight: 600;")
            else:
                rb["health"].setText("salute n/d")
                rb["health"].setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
            if b.cycle_count is not None:
                rb["cycles"].setText(f"cicli {b.cycle_count}")
            else:
                rb["cycles"].setText("cicli n/d")

        # Throttle
        rt = self._refs.get("throttle", {})
        if rt and s.throttle is not None:
            th = s.throttle
            if th.is_throttling or (th.last_seen_ago_s is not None and th.last_seen_ago_s < 30):
                rt["badge"].setText("THROTTLE!")
                rt["badge"].setStyleSheet(
                    f"color: white; background: {COLOR_RED}; "
                    "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
                )
                if th.is_throttling and not self._notified_throttle:
                    self._notify("⚠ CPU in thermal throttling")
                    self._notified_throttle = True
                    self.log.warning("CPU thermal throttling detected")
            else:
                rt["badge"].setText("OK")
                rt["badge"].setStyleSheet(
                    f"color: {COLOR_GREEN}; background: rgba(110,217,138,30); "
                    "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
                )
                if th.last_seen_ago_s is None or th.last_seen_ago_s > 60:
                    self._notified_throttle = False
            pkg = th.package_throttle_count
            core = th.core_throttle_count
            rt["counts"].setText(f"package: {pkg if pkg is not None else '—'} · "
                                  f"core: {core if core is not None else '—'}")
            if th.last_seen_ago_s is None:
                rt["last"].setText("Nessun evento dal boot")
            else:
                secs = th.last_seen_ago_s
                if secs < 60:
                    when = f"{int(secs)}s fa"
                elif secs < 3600:
                    when = f"{int(secs/60)}m fa"
                else:
                    when = f"{secs/3600:.1f}h fa"
                rt["last"].setText(f"Ultimo evento: {when}")

        # Fan service controls (formerly mbpfan section, now integrated in fan)
        if rf:
            if not mbpfan_ctrl.is_installed():
                rf["status"].setText("servizio non installato")
                rf["status"].setStyleSheet(f"color: {COLOR_ORANGE}; font-size: 10px;")
                if "btn_install" in rf: rf["btn_install"].setVisible(True)
                if "btn_restart" in rf: rf["btn_restart"].setEnabled(False)
                if "btn_tweaks" in rf: rf["btn_tweaks"].setEnabled(False)
                if "btn_curve" in rf: rf["btn_curve"].setEnabled(False)
                if "toggle" in rf: rf["toggle"].setEnabled(False)
                for b in self._preset_buttons.values():
                    b.setEnabled(False)
            else:
                status = mbpfan_ctrl.service_status()
                if self._manual_mode:
                    rf["status"].setText("override manuale")
                    rf["status"].setStyleSheet(f"color: {COLOR_ORANGE}; font-size: 10px; font-weight: 600;")
                else:
                    color = {"active": COLOR_GREEN, "failed": COLOR_RED,
                             "inactive": COLOR_ORANGE}.get(status, COLOR_ORANGE)
                    rf["status"].setText(status)
                    rf["status"].setStyleSheet(f"color: {color}; font-size: 10px;")
                if "btn_install" in rf: rf["btn_install"].setVisible(False)
                allow = not self._manual_mode
                if "btn_restart" in rf: rf["btn_restart"].setEnabled(allow)
                if "btn_tweaks" in rf: rf["btn_tweaks"].setEnabled(allow)
                if "btn_curve" in rf: rf["btn_curve"].setEnabled(allow)
                if "toggle" in rf: rf["toggle"].setEnabled(True)
                for b in self._preset_buttons.values():
                    b.setEnabled(allow)

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
        if not mbpfan_ctrl.is_installed():
            QMessageBox.warning(self, "mbpfan non installato", "Installa prima mbpfan.")
            self._refresh_preset_visual_state(); return
        if self._manual_mode:
            QMessageBox.information(self, "Override manuale attivo", "Disattiva prima l'override manuale.")
            self._refresh_preset_visual_state(); return
        import time as _t
        now = _t.monotonic()
        if hasattr(self, "_last_preset_t") and (now - self._last_preset_t) < 1.5:
            wait = 1.5 - (now - self._last_preset_t)
            self._notify(f"Attendi {wait:.0f}s")
            self._refresh_preset_visual_state(); return
        self._last_preset_t = now
        for b in self._preset_buttons.values(): b.setEnabled(False)
        QTimer.singleShot(1600, self._unlock_presets)
        ok, msg = mbpfan_ctrl.apply_preset(name)
        if not ok:
            QMessageBox.critical(self, "Errore", f"Preset {name} fallito:\n{msg}")
            self._refresh_preset_visual_state()
        else:
            self._notify(f"Preset {name} applicato")
            self.settings.active_preset = name
            config.save(self.settings)
            self._refresh_preset_visual_state()

    def _unlock_presets(self) -> None:
        if not self._manual_mode and mbpfan_ctrl.is_installed():
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
            QMessageBox.warning(self, "Libera RAM", f"Operazione fallita:\n{msg}"); return
        try:
            after = sensors.read_memory()
            aa = after.available_bytes if after else 0
        except Exception: aa = 0
        freed = max(0, aa - ab)
        self._notify(f"Liberati {sensors.format_bytes(freed)}" if freed > 0 else "Cache svuotata")

    # ---------------------------------------------------- manual override
    def _toggle_manual(self, on: bool) -> None:
        rf = self._refs.get("fan", {})
        if on:
            reply = QMessageBox.warning(
                self, "Attivazione override manuale",
                f"Disattivare mbpfan e prendere controllo manuale?\n\n"
                f"🛡 Sicurezza: sblocco automatico sopra {self.settings.manual_safety_temp_c}°C\n\n"
                f"Procedere?",
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
                QMessageBox.critical(self, "Errore", f"Impossibile attivare:\n{msg}")
                rf["toggle"].blockSignals(True); rf["toggle"].setChecked(False); rf["toggle"].blockSignals(False)
                return
            self._manual_mode = True
            rf["row"].setVisible(True)
            rf["toggle"].setText("Disattiva")
            rf["badge"].setText("ON")
            rf["badge"].setStyleSheet(
                f"color: #1a1a22; background: {COLOR_ORANGE}; "
                "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
            )
            self._clear_active_preset()
            self.manual_state_changed.emit(True)
            self._notify(f"Override manuale: {cur} RPM")
        else:
            ok, msg = mbpfan_ctrl.manual_off()
            self._manual_mode = False
            if "row" in rf: rf["row"].setVisible(False)
            rf["toggle"].setText("Attiva")
            rf["badge"].setText("OFF")
            rf["badge"].setStyleSheet(
                "color: rgba(255,255,255,140); background: rgba(255,255,255,12); "
                "border-radius: 6px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
            )
            self.manual_state_changed.emit(False)
            self._notify("Override manuale disattivato")

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
        if self.stress.running():
            QMessageBox.information(self, "Stress test", "Un test è già in corso."); return
        if not (StressTest.has_stress_ng() or StressTest.has_stress()):
            reply = QMessageBox.question(
                self, "stress-ng non installato",
                "Usare fallback Python (meno accurato)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes: return
        self.stress.start(duration)

    def _stop_stress(self) -> None:
        self.stress.stop()
        rs = self._refs.get("stress", {})
        if "status" in rs: rs["status"].setText("interrotto")
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
            QMessageBox.information(self, "Riavvio richiesto",
                                    "Cambio server grafico richiede riavvio app.")

    def _open_cleanup(self) -> None:
        from .cleanup_dialog import CleanupDialog
        CleanupDialog(self).exec()

    def _restart_mbpfan(self) -> None:
        ok, msg = mbpfan_ctrl.restart_service()
        if ok: self._notify("mbpfan riavviato")
        else: QMessageBox.critical(self, "Errore", f"Riavvio fallito:\n{msg}")

    def _install_mbpfan(self) -> None:
        reply = QMessageBox.question(self, "Installare mbpfan?",
                                      "Eseguire 'apt install mbpfan' tramite pkexec?")
        if reply != QMessageBox.StandardButton.Yes: return
        ok, msg = mbpfan_ctrl.install_mbpfan()
        if ok:
            self._notify("mbpfan installato"); mbpfan_ctrl.enable_service()
        else:
            QMessageBox.critical(self, "Errore", f"Installazione fallita:\n{msg}")

    def _show_governor_menu(self) -> None:
        avail = governor.available_governors()
        if not avail:
            QMessageBox.information(self, "Profilo CPU", "Nessun governor disponibile."); return
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
                text += "  (non disponibile)"
            act = menu.addAction(text)
            if target is None or target not in avail:
                act.setEnabled(False)
            else:
                act.triggered.connect(lambda _=False, p=label: self._set_profile(p))
        menu.addSeparator()
        info = menu.addAction(f"Governor reale: {governor.current_governor() or '—'}")
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
            QMessageBox.warning(self, "Profilo CPU", f"Impossibile applicare:\n{msg}")

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
        if self.isMaximized(): self.showNormal()
        else: self.showMaximized()

    # ------------------------------------------------------ events
    def wheelEvent(self, ev: QWheelEvent) -> None:  # noqa: N802
        delta = ev.angleDelta().y()
        step = 0.05 if delta > 0 else -0.05
        new_op = max(0.30, min(1.00, self.windowOpacity() + step))
        self.setWindowOpacity(new_op)
        self.settings.opacity = new_op
        config.save(self.settings)
        ev.accept()

    def contextMenuEvent(self, ev: QContextMenuEvent) -> None:  # noqa: N802
        menu = QMenu(self)
        op_menu = menu.addMenu("Trasparenza")
        for label, val in (("30%", 0.30), ("50%", 0.50), ("75%", 0.75), ("100%", 1.00)):
            act = op_menu.addAction(label); act.setCheckable(True)
            act.setChecked(abs(self.windowOpacity() - val) < 0.025)
            act.triggered.connect(lambda _=False, v=val: self._set_opacity(v))
        menu.addSeparator()
        pin_label = "Esci dalla modalità widget" if self._widget_mode else "Aggancia al desktop"
        menu.addAction(pin_label).triggered.connect(self.toggle_widget_mode)
        menu.addAction("Modalità mini").triggered.connect(self.enter_mini_mode)
        menu.addSeparator()
        menu.addAction("🔧 Modifica widget").triggered.connect(self._toggle_edit_mode)
        menu.addAction("⚙ Preferenze…").triggered.connect(self._open_preferences)
        menu.addSeparator()
        menu.addAction("Esci dal programma").triggered.connect(self.quit_requested.emit)
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
        if not self.isMaximized() and not self._widget_mode:
            self.settings.window_w = self.width(); self.settings.window_h = self.height()

    def _edge_at(self, pos: QPoint) -> Optional[str]:
        if self._widget_mode: return None
        m = RESIZE_MARGIN
        w, h = self.width(), self.height()
        left, right = pos.x() <= m, pos.x() >= w - m
        top, bottom = pos.y() <= m, pos.y() >= h - m
        if top and left: return "tl"
        if top and right: return "tr"
        if bottom and left: return "bl"
        if bottom and right: return "br"
        if left: return "l"
        if right: return "r"
        if top: return "t"
        if bottom: return "b"
        return None

    def _cursor_for_edge(self, edge: Optional[str]) -> Qt.CursorShape:
        return {
            "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
            "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
            "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
        }.get(edge, Qt.CursorShape.ArrowCursor)

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
        if not self._resize_start_geom or not self._resize_start_mouse: return
        dx = global_pos.x() - self._resize_start_mouse.x()
        dy = global_pos.y() - self._resize_start_mouse.y()
        g = QRect(self._resize_start_geom)
        min_w, min_h = 280, 420
        edge = self._resize_edge or ""
        if "l" in edge:
            new_left = min(g.left() + dx, g.right() - min_w); g.setLeft(new_left)
        if "r" in edge:
            g.setRight(max(g.left() + min_w, g.right() + dx))
        if "t" in edge:
            new_top = min(g.top() + dy, g.bottom() - min_h); g.setTop(new_top)
        if "b" in edge:
            g.setBottom(max(g.top() + min_h, g.bottom() + dy))
        self.setGeometry(g)
