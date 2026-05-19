"""
Mini-mode: a tiny always-on-top floating widget showing just temperature
and fan RPM. Designed to be unobtrusive (~160x52 px).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QFont, QMouseEvent, QContextMenuEvent
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QMenu

COLOR_GREEN = "#6ed98a"
COLOR_CYAN = "#7FD7FF"
COLOR_ORANGE = "#ffb454"
COLOR_RED_ORANGE = "#ff7a45"
COLOR_RED = "#ff5e57"


def _temp_color(t: Optional[float]) -> str:
    if t is None:
        return COLOR_CYAN
    if t < 50:
        return COLOR_GREEN
    if t < 65:
        return COLOR_CYAN
    if t < 78:
        return COLOR_ORANGE
    if t < 90:
        return COLOR_RED_ORANGE
    return COLOR_RED


class MiniWindow(QWidget):
    closed = Signal()
    expand_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fresh Fan Manager · mini")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.Tool
                 | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlags(flags)
        self.setFixedSize(178, 64)

        self._drag_pos: Optional[QPoint] = None

        root = QWidget(self)
        root.setObjectName("miniRoot")
        root.setGeometry(0, 0, 178, 64)
        root.setStyleSheet(
            "QWidget#miniRoot { "
            "background: rgba(20,22,30,235); "
            "border: 1px solid rgba(127,215,255,80); "
            "border-radius: 10px; "
            "}"
        )

        lay = QHBoxLayout(root)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(10)

        # Snowflake icon + temp
        left = QVBoxLayout()
        left.setSpacing(0)
        self.flake = QLabel("❄")
        flake_f = QFont(self.flake.font())
        flake_f.setPixelSize(32)
        flake_f.setBold(True)
        self.flake.setFont(flake_f)
        self.flake.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.flake.setStyleSheet(f"color: {COLOR_CYAN};")
        left.addWidget(self.flake)
        lay.addLayout(left)

        # Temp + fan stacked
        mid = QVBoxLayout()
        mid.setSpacing(0)
        self.temp_label = QLabel("—°")
        tf = QFont(self.temp_label.font())
        tf.setPixelSize(26); tf.setBold(True)
        self.temp_label.setFont(tf)
        self.temp_label.setStyleSheet(f"color: {COLOR_CYAN};")
        mid.addWidget(self.temp_label)
        self.fan_label = QLabel("— RPM")
        self.fan_label.setStyleSheet("color: rgba(255,255,255,170); font-size: 10px;")
        mid.addWidget(self.fan_label)
        lay.addLayout(mid, 1)

    def update_values(self, temp: Optional[float], fan_rpm: Optional[int]) -> None:
        if temp is not None:
            color = _temp_color(temp)
            self.temp_label.setText(f"{temp:.0f}°")
            self.temp_label.setStyleSheet(f"color: {color};")
            self.flake.setStyleSheet(f"color: {color};")
        if fan_rpm is not None:
            self.fan_label.setText(f"{fan_rpm} RPM")

    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if self._drag_pos and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        self.expand_requested.emit()

    def contextMenuEvent(self, ev: QContextMenuEvent) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.addAction("↗ Apri finestra completa").triggered.connect(self.expand_requested.emit)
        menu.addSeparator()
        menu.addAction("✕ Chiudi mini-mode").triggered.connect(self.closed.emit)
        menu.exec(ev.globalPos())
