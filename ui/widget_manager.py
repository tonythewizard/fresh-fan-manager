# SPDX-License-Identifier: GPL-3.0-or-later
"""
Widget manager — handles the orderable/hidable sections of the main window.

Each registered "widget section" is a QWidget identified by a string key.
The manager:
  * exposes an edit mode with iPhone-style long-press to edit, jiggle animation,
    and circular (✕) removal badges
  * reorders sections via direct drag-and-drop anywhere on the widget card
  * supports per-widget sizing (compact / normal / expanded)
  * supports the Essentials Divider ("Linea degli Essenziali") to split compact vs extended view
  * persists order, visibility, size, and view_mode via core.config
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (Qt, QPoint, QMimeData, QSize, Signal, QObject,
                              QRectF, QTimer, QEvent)
from PySide6.QtGui import (QDrag, QPixmap, QPainter, QMouseEvent, QPen,
                            QColor, QLinearGradient, QFont)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QFrame, QMenu, QSizePolicy)

from core import config
from core.i18n import tr

COLOR_CYAN = "#7FD7FF"
COLOR_RED = "#ff5e57"
COLOR_GREEN = "#6ed98a"
COLOR_AMBER = "#ffb454"


class SectionLabelsDict(dict):
    def get(self, key, default=None):
        label_map = {
            "cpu":                  tr("sec_cpu"),
            "fan":                  tr("sec_fan"),
            "maintenance":          tr("sec_maintenance"),
            "ram":                  tr("sec_ram"),
            "gpu_battery":          tr("sec_gpu_battery"),
            "throttle":             tr("sec_throttle"),
            "disk":                 tr("sec_disk"),
            "stress":               tr("sec_stress"),
            "network":              tr("sec_network"),
            "power":                tr("sec_power"),
            "cpu_cores":            tr("sec_cpu_cores"),
            "quick_controls":       tr("sec_quick_controls"),
            "__essentials_divider__": tr("essentials_divider"),
        }
        return label_map.get(key, default or key)


SECTION_LABELS = SectionLabelsDict()


class IOSBadgeButton(QPushButton):
    """Circular floating '✕' removal badge in iPhone jiggle style."""

    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Rimuovi / Remove")
        self.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff6565, stop:1 #e03131);"
            "  color: white;"
            "  font-weight: 800;"
            "  font-size: 11px;"
            "  border: 1.5px solid white;"
            "  border-radius: 10px;"
            "  padding: 0px;"
            "}"
            "QPushButton:hover {"
            "  background: #ff4757;"
            "  border: 1.5px solid #7FD7FF;"
            "}"
            "QPushButton:pressed {"
            "  background: #c92a2a;"
            "}"
        )


class SlotLongPressFilter(QObject):
    """Detects mouse hold (long press ~420ms) directly from the UI
    to trigger iPhone-style edit/jiggle mode."""

    def __init__(self, slot: "WidgetSlot"):
        super().__init__(slot)
        self.slot = slot
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(420)
        self.timer.timeout.connect(self._on_timeout)
        self._press_pos = QPoint()
        self._global_press_pos = QPoint()
        self._is_down = False

    def _on_timeout(self) -> None:
        if self._is_down:
            self.slot.trigger_long_press(self._press_pos)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                if self.slot.manager.is_edit_mode():
                    return False
                self._is_down = True
                self._press_pos = self.slot.mapFromGlobal(event.globalPosition().toPoint())
                self._global_press_pos = event.globalPosition().toPoint()
                self.timer.start()
        elif etype == QEvent.Type.MouseMove:
            if self._is_down:
                dist = (event.globalPosition().toPoint() - self._global_press_pos).manhattanLength()
                if dist > 10:
                    self._is_down = False
                    self.timer.stop()
        elif etype in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
            self._is_down = False
            self.timer.stop()
        return False


class EssentialsDividerWidget(QWidget):
    """Visual divider separating essential compact widgets from extended widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        self.setFixedHeight(22)
        self.setAutoFillBackground(False)

    def set_edit_mode(self, on: bool) -> None:
        self._edit_mode = on
        self.setFixedHeight(26 if on else 16)
        self.update()

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = self.height()
        cy = h / 2.0

        try:
            win = self.window()
            theme = getattr(win.settings, "theme", "dark")
        except Exception:
            theme = "dark"

        if theme in ("light", "solarized_light"):
            accent_col = QColor(9, 105, 218)
            hair_col = QColor(0, 0, 0, 45)
        elif theme == "sepia":
            accent_col = QColor(160, 82, 45)
            hair_col = QColor(120, 85, 45, 50)
        elif theme == "hicontrast":
            accent_col = QColor(255, 255, 0)
            hair_col = QColor(255, 255, 255, 180)
        elif theme == "solarized_dark":
            accent_col = QColor(38, 139, 210)
            hair_col = QColor(147, 161, 161, 60)
        else:  # dark
            accent_col = QColor(127, 215, 255)
            hair_col = QColor(255, 255, 255, 40)

        if self._edit_mode:
            # Glowing dashed divider with text in edit mode
            grad = QLinearGradient(0, cy, w, cy)
            c_low = QColor(accent_col)
            c_low.setAlpha(40)
            c_hi = QColor(accent_col)
            c_hi.setAlpha(240)
            grad.setColorAt(0.0, c_low)
            grad.setColorAt(0.5, c_hi)
            grad.setColorAt(1.0, c_low)
            pen = QPen(grad, 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(10, int(cy), w - 10, int(cy))

            # Center badge
            badge_text = tr("essentials_divider")
            f = QFont(self.font())
            f.setPixelSize(10)
            f.setBold(True)
            p.setFont(f)
            p.setPen(c_hi)
            rect = QRectF(0, 0, w, h)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, badge_text)
        else:
            # Subtle hairline divider in normal All mode
            grad = QLinearGradient(0, cy, w, cy)
            grad.setColorAt(0.0, QColor(hair_col.red(), hair_col.green(), hair_col.blue(), 0))
            grad.setColorAt(0.3, hair_col)
            c_mid = QColor(accent_col)
            c_mid.setAlpha(120)
            grad.setColorAt(0.5, c_mid)
            grad.setColorAt(0.7, hair_col)
            grad.setColorAt(1.0, QColor(hair_col.red(), hair_col.green(), hair_col.blue(), 0))
            pen = QPen(grad, 1.0)
            p.setPen(pen)
            p.drawLine(20, int(cy), w - 20, int(cy))


class WidgetSlot(QFrame):
    """Container around a section widget. Adds drag handle, density/size buttons,
    iPhone-style circular removal badge, and long-press edit trigger."""

    move_requested = Signal(str, str)  # (source_key, target_key)

    def __init__(self, key: str, content: QWidget, manager: "WidgetManager", current_size: str = "normal"):
        super().__init__()
        self.key = key
        self.manager = manager
        self.content = content
        self.current_size = current_size
        self.setProperty("class", "widget-slot")
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
            f"color: {COLOR_CYAN}; font-size: 14px; font-weight: 700; padding: 0 4px;"
        )
        self.handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self.handle.setToolTip("Trascina per riordinare / Drag to reorder")
        tb_lay.addWidget(self.handle)

        name = QLabel(SECTION_LABELS.get(key, key))
        name.setStyleSheet("color: rgba(255,255,255,185); font-size: 11px; font-weight: 600;")
        tb_lay.addWidget(name)
        tb_lay.addStretch()

        is_divider = (key == "__essentials_divider__")

        if not is_divider:
            # Sizing pill
            self.btn_sz_compact = QPushButton("−")
            self.btn_sz_normal = QPushButton("=")
            self.btn_sz_expanded = QPushButton("+")
            for b, sz, tip in [
                (self.btn_sz_compact, "compact", tr("size_compact")),
                (self.btn_sz_normal, "normal", tr("size_normal")),
                (self.btn_sz_expanded, "expanded", tr("size_expanded")),
            ]:
                b.setFixedSize(18, 18)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setToolTip(f"{SECTION_LABELS.get(key, key)}: {tip}")
                b.clicked.connect(lambda _=False, k=key, s=sz: manager.set_widget_size(k, s))
                tb_lay.addWidget(b)

            self.update_size_buttons(current_size)

            # iPhone-style circular '✕' removal badge
            self.badge_close = IOSBadgeButton()
            self.badge_close.clicked.connect(lambda: manager.hide_section(key))
            tb_lay.addWidget(self.badge_close)

        outer.addWidget(self.toolbar)
        outer.addWidget(content)

        # Direct UI long-press listener
        self._long_press_filter = SlotLongPressFilter(self)
        self.installEventFilter(self._long_press_filter)
        self._install_content_filter()

    def _install_content_filter(self) -> None:
        self.content.installEventFilter(self._long_press_filter)
        for child in self.content.findChildren(QWidget):
            child.installEventFilter(self._long_press_filter)

    def trigger_long_press(self, pos: QPoint) -> None:
        """Triggered when holding down for >420ms on the widget."""
        self.manager.set_edit_mode(True)
        self._drag_start = pos

    def update_size_buttons(self, size: str) -> None:
        self.current_size = size
        if hasattr(self, "btn_sz_compact"):
            active_style = (
                f"background: rgba(127,215,255,70); color: {COLOR_CYAN}; "
                "border: 1px solid #7FD7FF; border-radius: 4px; font-size: 11px; font-weight: 700;"
            )
            inactive_style = (
                "background: rgba(255,255,255,14); color: rgba(255,255,255,140); "
                "border: 1px solid rgba(255,255,255,20); border-radius: 4px; font-size: 11px;"
            )
            self.btn_sz_compact.setStyleSheet(active_style if size == "compact" else inactive_style)
            self.btn_sz_normal.setStyleSheet(active_style if size == "normal" else inactive_style)
            self.btn_sz_expanded.setStyleSheet(active_style if size == "expanded" else inactive_style)

    def set_wiggle_offset(self, dx: int) -> None:
        """Subtle horizontal nudge for the iOS jiggle animation."""
        if self.key == "__essentials_divider__":
            return
        if dx < 0:
            self.setContentsMargins(0, 0, 2, 0)
        elif dx > 0:
            self.setContentsMargins(2, 0, 0, 0)
        else:
            self.setContentsMargins(0, 0, 0, 0)

    def set_edit_mode(self, on: bool) -> None:
        self.toolbar.setVisible(on)
        if hasattr(self.content, "set_edit_mode"):
            self.content.set_edit_mode(on)
        if on:
            self.setStyleSheet(
                "QFrame[class='widget-slot'] { "
                "border: 1px dashed rgba(127,215,255,90); border-radius: 8px; }"
            )
        else:
            self.setContentsMargins(0, 0, 0, 0)
            self.setStyleSheet("")

    # -------- drag source --------
    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if self.manager.is_edit_mode() and ev.button() == Qt.MouseButton.LeftButton:
            # In edit mode, allow dragging from anywhere on the card!
            self._drag_start = ev.position().toPoint()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if (self._drag_start is not None
                and (ev.position().toPoint() - self._drag_start).manhattanLength() > 6):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(self.key)
            drag.setMimeData(mime)
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
                "border: 2px solid #7FD7FF; border-radius: 8px; "
                "background: rgba(127,215,255,22); }"
            )

    def dragLeaveEvent(self, ev) -> None:  # noqa: N802
        if self.toolbar.isVisible():
            self.setStyleSheet(
                "QFrame[class='widget-slot'] { "
                "border: 1px dashed rgba(127,215,255,90); border-radius: 8px; }"
            )

    def dropEvent(self, ev) -> None:  # noqa: N802
        src = ev.mimeData().text()
        if src and src != self.key:
            self.move_requested.emit(src, self.key)
            ev.acceptProposedAction()
        if self.toolbar.isVisible():
            self.setStyleSheet(
                "QFrame[class='widget-slot'] { "
                "border: 1px dashed rgba(127,215,255,90); border-radius: 8px; }"
            )


class WidgetManager(QObject):
    """Manages the collection of WidgetSlots inside a host layout."""

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

        # iOS-style lightweight jiggle timer (runs only while editing)
        self._wiggle_timer = QTimer(self)
        self._wiggle_timer.setInterval(90)
        self._wiggle_timer.timeout.connect(self._on_wiggle_tick)
        self._wiggle_step = 0

        self._rebuild_all()

    def _rebuild_all(self) -> None:
        # Clear existing
        while self.host_layout.count():
            item = self.host_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.slots.clear()

        # Build in saved order
        for key in self.settings.widget_order:
            if not self.settings.widget_visible.get(key, True):
                continue

            # Essentials mode filtering: in normal mode, hide everything past divider
            if self.settings.view_mode == "essentials" and not self._edit_mode:
                if key == "__essentials_divider__":
                    break

            # In All mode when not editing, the divider is hidden so all widgets show seamlessly
            if key == "__essentials_divider__" and not self._edit_mode:
                continue

            if key not in self.builders:
                continue

            content = self.builders[key]()
            size = self.settings.widget_sizes.get(key, "normal")
            if hasattr(content, "set_density"):
                content.set_density(size)

            slot = WidgetSlot(key, content, self, current_size=size)
            slot.set_edit_mode(self._edit_mode)
            slot.move_requested.connect(self._on_move_requested)
            self.slots[key] = slot
            self.host_layout.addWidget(slot)

    def _on_wiggle_tick(self) -> None:
        if not self._edit_mode:
            return
        self._wiggle_step += 1
        offsets = [-1, 1]
        for idx, slot in enumerate(self.slots.values()):
            phase = (self._wiggle_step + idx) % 2
            slot.set_wiggle_offset(offsets[phase])

    # ----------------------------- public API ---------------------------
    def is_edit_mode(self) -> bool:
        return self._edit_mode

    def set_edit_mode(self, on: bool) -> None:
        if self._edit_mode == on:
            return
        self._edit_mode = on
        self._rebuild_all()
        for slot in self.slots.values():
            slot.set_edit_mode(on)
        if on:
            self._wiggle_step = 0
            self._wiggle_timer.start()
        else:
            self._wiggle_timer.stop()
            for slot in self.slots.values():
                slot.set_wiggle_offset(0)
        self.edit_mode_changed.emit(on)

    def set_widget_size(self, key: str, size: str) -> None:
        self.settings.widget_sizes[key] = size
        config.save(self.settings)
        content = self.get_content(key)
        if content and hasattr(content, "set_density"):
            content.set_density(size)
        if key in self.slots:
            self.slots[key].update_size_buttons(size)
        self.layout_changed.emit()

    def set_view_mode(self, mode: str) -> None:
        if mode not in ("all", "essentials"):
            mode = "all"
        self.settings.view_mode = mode
        config.save(self.settings)
        self._rebuild_all()
        if self._edit_mode:
            for s in self.slots.values():
                s.set_edit_mode(True)
        self.layout_changed.emit()

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
        order = list(self.settings.widget_order)
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
