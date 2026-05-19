"""
Widget manager — handles the orderable/hidable sections of the main window.

Each registered "widget section" is just a QWidget identified by a string key.
The manager:
  * exposes an edit mode that wraps each section with handle/close controls
  * reorders sections via drag-and-drop (in edit mode)
  * persists order + visibility via core.config
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (Qt, QPoint, QMimeData, QSize, Signal, QObject,
                              QPropertyAnimation, QEasingCurve, QRect)
from PySide6.QtGui import (QDrag, QPixmap, QPainter, QMouseEvent, QPaintEvent,
                            QColor)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QFrame, QMenu, QSizePolicy,
                                QGraphicsOpacityEffect)

from core import config

# Friendly names shown in the "+" add menu
SECTION_LABELS = {
    "cpu":          "CPU + Temperatura",
    "fan":          "Ventola",
    "maintenance":  "Pulizia & manutenzione",
    "ram":          "RAM",
    "gpu_battery":  "GPU + Batteria",
    "throttle":     "Throttling",
    "disk":         "Disco (SMART)",
    "stress":       "Stress test",
}

COLOR_CYAN = "#7FD7FF"
COLOR_RED = "#ff5e57"


class WidgetSlot(QFrame):
    """Container around a section widget. Adds drag handle + close button
    when in edit mode."""

    move_requested = Signal(str, str)  # (source_key, target_key)

    def __init__(self, key: str, content: QWidget, manager: "WidgetManager"):
        super().__init__()
        self.key = key
        self.manager = manager
        self.content = content
        self.setProperty("class", "widget-slot")
        self.setAcceptDrops(True)
        self._drag_start: Optional[QPoint] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Edit-mode toolbar (hidden in normal mode)
        self.toolbar = QWidget()
        self.toolbar.setVisible(False)
        tb_lay = QHBoxLayout(self.toolbar)
        tb_lay.setContentsMargins(6, 2, 6, 2)
        tb_lay.setSpacing(6)

        self.handle = QLabel("⋮⋮")
        self.handle.setStyleSheet(
            f"color: {COLOR_CYAN}; font-size: 14px; font-weight: 700; "
            "padding: 0 4px;"
        )
        self.handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self.handle.setToolTip("Trascina per spostare")
        tb_lay.addWidget(self.handle)

        name = QLabel(SECTION_LABELS.get(key, key))
        name.setStyleSheet("color: rgba(255,255,255,160); font-size: 10px;")
        tb_lay.addWidget(name)
        tb_lay.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Nascondi questa sezione")
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {COLOR_RED}; "
            "border: none; font-weight: 700; font-size: 12px; }}"
            f"QPushButton:hover {{ background: rgba(255,94,87,40); border-radius: 10px; }}"
        )
        close_btn.clicked.connect(lambda: manager.hide_section(key))
        tb_lay.addWidget(close_btn)

        outer.addWidget(self.toolbar)
        outer.addWidget(content)

    def set_edit_mode(self, on: bool) -> None:
        self.toolbar.setVisible(on)
        if on:
            self.setStyleSheet(
                "QFrame[class='widget-slot'] { "
                "border: 1px dashed rgba(127,215,255,90); border-radius: 6px; }"
            )
        else:
            self.setStyleSheet("")

    # -------- drag source --------
    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if (self.toolbar.isVisible() and ev.button() == Qt.MouseButton.LeftButton
                and self.handle.geometry().contains(ev.position().toPoint())):
            self._drag_start = ev.position().toPoint()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if (self._drag_start is not None
                and (ev.position().toPoint() - self._drag_start).manhattanLength() > 10):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(self.key)
            drag.setMimeData(mime)
            # Visual: snapshot of this slot at lower opacity
            pm = self.grab()
            sm = pm.scaledToWidth(min(pm.width(), 280),
                                  Qt.TransformationMode.SmoothTransformation)
            drag.setPixmap(sm)
            drag.setHotSpot(QPoint(20, 14))
            self._drag_start = None
            drag.exec(Qt.DropAction.MoveAction)
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        self._drag_start = None
        super().mouseReleaseEvent(ev)

    # -------- drop target --------
    def dragEnterEvent(self, ev) -> None:  # noqa: N802
        if self.toolbar.isVisible() and ev.mimeData().hasText():
            ev.acceptProposedAction()
            self.setStyleSheet(
                "QFrame[class='widget-slot'] { "
                "border: 2px solid #7FD7FF; border-radius: 6px; "
                "background: rgba(127,215,255,18); }"
            )

    def dragLeaveEvent(self, ev) -> None:  # noqa: N802
        if self.toolbar.isVisible():
            self.setStyleSheet(
                "QFrame[class='widget-slot'] { "
                "border: 1px dashed rgba(127,215,255,90); border-radius: 6px; }"
            )

    def dropEvent(self, ev) -> None:  # noqa: N802
        src = ev.mimeData().text()
        if src and src != self.key:
            self.move_requested.emit(src, self.key)
            ev.acceptProposedAction()
        # restore style
        if self.toolbar.isVisible():
            self.setStyleSheet(
                "QFrame[class='widget-slot'] { "
                "border: 1px dashed rgba(127,215,255,90); border-radius: 6px; }"
            )


class WidgetManager(QObject):
    """Manages the collection of WidgetSlot inside a host layout."""

    edit_mode_changed = Signal(bool)
    layout_changed = Signal()

    def __init__(self, settings: config.Settings, host_layout: QVBoxLayout,
                 builders: dict[str, Callable[[], QWidget]]):
        super().__init__()
        self.settings = settings
        self.host_layout = host_layout
        self.builders = builders
        self.slots: dict[str, WidgetSlot] = {}
        self._edit_mode = False
        self._rebuild_all()

    def _rebuild_all(self) -> None:
        # Clear existing
        while self.host_layout.count():
            item = self.host_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self.slots.clear()
        # Insert in saved order, only visible ones
        for key in self.settings.widget_order:
            if not self.settings.widget_visible.get(key, True):
                continue
            if key not in self.builders:
                continue
            content = self.builders[key]()
            slot = WidgetSlot(key, content, self)
            slot.set_edit_mode(self._edit_mode)
            slot.move_requested.connect(self._on_move_requested)
            self.slots[key] = slot
            self.host_layout.addWidget(slot)

    # ----------------------------- public API ---------------------------
    def is_edit_mode(self) -> bool:
        return self._edit_mode

    def set_edit_mode(self, on: bool) -> None:
        self._edit_mode = on
        for slot in self.slots.values():
            slot.set_edit_mode(on)
        self.edit_mode_changed.emit(on)

    def hide_section(self, key: str) -> None:
        self.settings.widget_visible[key] = False
        config.save(self.settings)
        self._rebuild_all()
        if self._edit_mode:
            for s in self.slots.values():
                s.set_edit_mode(True)
        self.layout_changed.emit()

    def show_section(self, key: str) -> None:
        self.settings.widget_visible[key] = True
        if key not in self.settings.widget_order:
            self.settings.widget_order.append(key)
        config.save(self.settings)
        self._rebuild_all()
        if self._edit_mode:
            for s in self.slots.values():
                s.set_edit_mode(True)
        self.layout_changed.emit()

    def hidden_sections(self) -> list[str]:
        return [k for k in self.settings.widget_order
                if not self.settings.widget_visible.get(k, True)
                and k in self.builders]

    def _on_move_requested(self, src: str, dst: str) -> None:
        order = self.settings.widget_order
        if src not in order or dst not in order:
            return
        order.remove(src)
        order.insert(order.index(dst), src)
        self.settings.widget_order = order
        config.save(self.settings)
        self._rebuild_all()
        if self._edit_mode:
            for s in self.slots.values():
                s.set_edit_mode(True)
        self.layout_changed.emit()

    def get_content(self, key: str) -> Optional[QWidget]:
        slot = self.slots.get(key)
        return slot.content if slot else None
