"""
Visual fan curve editor.

The user drags two control points on a temperature/RPM chart:
- "low" point: (low_temp, min_rpm) — fan starts ramping up from here
- "high" point: (high_temp, max_rpm) — fan reaches full speed at this temp

Above `max_temp` (a third spinbox) the fan is forced to max as an emergency
cap. The output maps directly to mbpfan.conf parameters, so we apply changes
by reusing the existing tweak machinery — no need for a custom daemon.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QRectF, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QMouseEvent,
                            QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QSpinBox, QWidget, QMessageBox,
                                QFormLayout)

from core import mbpfan_ctrl
from core.mbpfan_ctrl import MbpfanConfig


@dataclass
class CurvePoint:
    temp: int   # °C
    rpm: int


class FanCurveCanvas(QWidget):
    """Draggable two-point curve editor on a temp/RPM grid."""
    changed = Signal()

    TEMP_MIN = 30
    TEMP_MAX = 100

    def __init__(self, fan_min: int = 1200, fan_max: int = 6500, parent=None):
        super().__init__(parent)
        self._fan_min = fan_min
        self._fan_max = fan_max
        self._low = CurvePoint(temp=50, rpm=fan_min)
        self._high = CurvePoint(temp=72, rpm=fan_max)
        self._dragging: Optional[str] = None  # "low" | "high" | None
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def points(self) -> tuple[CurvePoint, CurvePoint]:
        return self._low, self._high

    def set_points(self, low: CurvePoint, high: CurvePoint) -> None:
        self._low = low
        self._high = high
        self.update()
        self.changed.emit()

    # ---------- mapping coords <-> data ----------
    def _plot_rect(self) -> QRectF:
        return QRectF(40, 12, self.width() - 50, self.height() - 36)

    def _t_to_x(self, t: int) -> float:
        r = self._plot_rect()
        return r.left() + (t - self.TEMP_MIN) / (self.TEMP_MAX - self.TEMP_MIN) * r.width()

    def _x_to_t(self, x: float) -> int:
        r = self._plot_rect()
        if r.width() <= 0:
            return self.TEMP_MIN
        v = (x - r.left()) / r.width() * (self.TEMP_MAX - self.TEMP_MIN) + self.TEMP_MIN
        return int(max(self.TEMP_MIN, min(self.TEMP_MAX, v)))

    def _rpm_to_y(self, rpm: int) -> float:
        r = self._plot_rect()
        rng = max(1, self._fan_max - self._fan_min)
        return r.bottom() - (rpm - self._fan_min) / rng * r.height()

    def _y_to_rpm(self, y: float) -> int:
        r = self._plot_rect()
        if r.height() <= 0:
            return self._fan_min
        v = (r.bottom() - y) / r.height() * (self._fan_max - self._fan_min) + self._fan_min
        v = max(self._fan_min, min(self._fan_max, v))
        return (int(v) // 50) * 50

    # ---------- painting ----------
    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._plot_rect()

        # Background panel
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 14))
        p.drawRoundedRect(r, 6, 6)

        # Grid lines: vertical (every 10°C), horizontal (every 1000 RPM)
        grid_pen = QPen(QColor(255, 255, 255, 30))
        grid_pen.setWidth(1)
        p.setPen(grid_pen)
        for t in range(self.TEMP_MIN, self.TEMP_MAX + 1, 10):
            x = self._t_to_x(t)
            p.drawLine(int(x), int(r.top()), int(x), int(r.bottom()))
        rpm = ((self._fan_min // 1000) + 1) * 1000
        while rpm <= self._fan_max:
            y = self._rpm_to_y(rpm)
            p.drawLine(int(r.left()), int(y), int(r.right()), int(y))
            rpm += 1000

        # Axis labels
        label_pen = QPen(QColor(255, 255, 255, 160))
        p.setPen(label_pen)
        f = QFont(); f.setPixelSize(9); p.setFont(f)
        for t in range(self.TEMP_MIN, self.TEMP_MAX + 1, 10):
            x = self._t_to_x(t)
            p.drawText(int(x) - 9, int(r.bottom()) + 14, f"{t}°")
        for rpm_l in (self._fan_min, (self._fan_min + self._fan_max) // 2, self._fan_max):
            y = self._rpm_to_y(rpm_l)
            p.drawText(2, int(y) + 3, f"{rpm_l}")

        # Curve: piecewise line from (TEMP_MIN, fan_min) -> low -> high -> (TEMP_MAX, fan_max)
        path = QPainterPath()
        path.moveTo(r.left(), self._rpm_to_y(self._fan_min))
        path.lineTo(self._t_to_x(self._low.temp), self._rpm_to_y(self._low.rpm))
        path.lineTo(self._t_to_x(self._high.temp), self._rpm_to_y(self._high.rpm))
        path.lineTo(r.right(), self._rpm_to_y(self._fan_max))

        # Filled area under curve
        fill_path = QPainterPath(path)
        fill_path.lineTo(r.right(), r.bottom())
        fill_path.lineTo(r.left(), r.bottom())
        fill_path.closeSubpath()
        grad = QLinearGradient(0, r.top(), 0, r.bottom())
        grad.setColorAt(0.0, QColor(127, 215, 255, 80))
        grad.setColorAt(1.0, QColor(127, 215, 255, 0))
        p.fillPath(fill_path, grad)

        line_pen = QPen(QColor("#7FD7FF"))
        line_pen.setWidthF(2.0)
        p.setPen(line_pen)
        p.drawPath(path)

        # Control points (draggable)
        for cp, label in ((self._low, "low"), (self._high, "high")):
            x, y = self._t_to_x(cp.temp), self._rpm_to_y(cp.rpm)
            p.setBrush(QColor("#7FD7FF"))
            p.setPen(QPen(QColor("#0b1b24"), 2))
            p.drawEllipse(QPoint(int(x), int(y)), 7, 7)
            # readout
            txt_pen = QPen(QColor(255, 255, 255, 220))
            p.setPen(txt_pen)
            txt_font = QFont(); txt_font.setPixelSize(10); txt_font.setBold(True)
            p.setFont(txt_font)
            p.drawText(int(x) + 10, int(y) + 4, f"{cp.temp}° / {cp.rpm}")

    # ---------- interaction ----------
    def _hit_point(self, pos: QPoint) -> Optional[str]:
        def near(cp):
            cx, cy = self._t_to_x(cp.temp), self._rpm_to_y(cp.rpm)
            return abs(pos.x() - cx) <= 12 and abs(pos.y() - cy) <= 12
        if near(self._low):
            return "low"
        if near(self._high):
            return "high"
        return None

    def mousePressEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._dragging = self._hit_point(ev.position().toPoint())
            ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        self._dragging = None

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:  # noqa: N802
        if self._dragging is None:
            self.setCursor(Qt.CursorShape.PointingHandCursor
                           if self._hit_point(ev.position().toPoint())
                           else Qt.CursorShape.ArrowCursor)
            return
        pos = ev.position().toPoint()
        t = self._x_to_t(pos.x())
        r = self._y_to_rpm(pos.y())
        if self._dragging == "low":
            # low must stay below high on both axes
            t = min(t, self._high.temp - 2)
            r = min(r, self._high.rpm - 100)
            self._low = CurvePoint(temp=t, rpm=r)
        else:
            t = max(t, self._low.temp + 2)
            r = max(r, self._low.rpm + 100)
            self._high = CurvePoint(temp=t, rpm=r)
        self.update()
        self.changed.emit()


class FanCurveDialog(QDialog):
    def __init__(self, parent=None, fan_min: int = 1200, fan_max: int = 6500):
        super().__init__(parent)
        self.setWindowTitle("Curva ventola personalizzata")
        self.setMinimumWidth(540)

        cfg = mbpfan_ctrl.read_config()
        self._fan_min = fan_min
        self._fan_max = fan_max

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        info = QLabel(
            "Trascina i due punti per definire la curva. La ventola partirà al minimo "
            "fino al punto basso, crescerà linearmente fino al punto alto, "
            "e raggiungerà il massimo da lì in poi. Il valore Max temp è un cap "
            "di sicurezza separato."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: rgba(255,255,255,160); font-size: 11px;")
        layout.addWidget(info)

        self.canvas = FanCurveCanvas(fan_min=fan_min, fan_max=fan_max)
        # Seed from current config
        low_rpm = cfg.min_fan1_speed if cfg.min_fan1_speed else fan_min
        high_rpm = cfg.max_fan1_speed if cfg.max_fan1_speed else fan_max
        self.canvas.set_points(
            CurvePoint(temp=cfg.low_temp, rpm=low_rpm),
            CurvePoint(temp=cfg.high_temp, rpm=high_rpm),
        )
        self.canvas.changed.connect(self._sync_spinboxes)
        layout.addWidget(self.canvas)

        # Spinbox rows for fine-grained editing
        form = QFormLayout()
        form.setSpacing(6)

        self.sp_low_t = QSpinBox(); self.sp_low_t.setRange(self.canvas.TEMP_MIN, 90); self.sp_low_t.setSuffix(" °C")
        self.sp_low_r = QSpinBox(); self.sp_low_r.setRange(fan_min, fan_max); self.sp_low_r.setSuffix(" RPM"); self.sp_low_r.setSingleStep(50)
        self.sp_high_t = QSpinBox(); self.sp_high_t.setRange(40, 95); self.sp_high_t.setSuffix(" °C")
        self.sp_high_r = QSpinBox(); self.sp_high_r.setRange(fan_min, fan_max); self.sp_high_r.setSuffix(" RPM"); self.sp_high_r.setSingleStep(50)
        self.sp_max_t = QSpinBox(); self.sp_max_t.setRange(60, 105); self.sp_max_t.setSuffix(" °C"); self.sp_max_t.setValue(cfg.max_temp)
        self.sp_poll = QSpinBox(); self.sp_poll.setRange(1, 30); self.sp_poll.setSuffix(" s"); self.sp_poll.setValue(cfg.polling_interval)

        row_low = QHBoxLayout()
        row_low.addWidget(QLabel("Punto basso:"))
        row_low.addWidget(self.sp_low_t)
        row_low.addWidget(self.sp_low_r)
        layout.addLayout(row_low)
        row_high = QHBoxLayout()
        row_high.addWidget(QLabel("Punto alto:"))
        row_high.addWidget(self.sp_high_t)
        row_high.addWidget(self.sp_high_r)
        layout.addLayout(row_high)
        row_misc = QHBoxLayout()
        row_misc.addWidget(QLabel("Max temp (cap):"))
        row_misc.addWidget(self.sp_max_t)
        row_misc.addWidget(QLabel("  Polling:"))
        row_misc.addWidget(self.sp_poll)
        row_misc.addStretch()
        layout.addLayout(row_misc)

        # Initial sync
        self._sync_spinboxes()

        for sp in (self.sp_low_t, self.sp_low_r, self.sp_high_t, self.sp_high_r):
            sp.valueChanged.connect(self._sync_canvas)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel = QPushButton("Annulla")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply = QPushButton("Applica e riavvia mbpfan")
        self.btn_apply.setDefault(True)
        self.btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_apply)
        layout.addLayout(btn_row)
        try:
            from core import config as _cfg
            from .painted_frames import retint_labels
            retint_labels(self, _cfg.load().theme)
        except Exception:
            pass

    def _sync_spinboxes(self) -> None:
        low, high = self.canvas.points()
        for sp, v in ((self.sp_low_t, low.temp), (self.sp_low_r, low.rpm),
                      (self.sp_high_t, high.temp), (self.sp_high_r, high.rpm)):
            sp.blockSignals(True); sp.setValue(v); sp.blockSignals(False)

    def _sync_canvas(self) -> None:
        # Enforce ordering
        if self.sp_low_t.value() >= self.sp_high_t.value():
            self.sp_low_t.setValue(self.sp_high_t.value() - 2)
        if self.sp_low_r.value() >= self.sp_high_r.value():
            self.sp_low_r.setValue(self.sp_high_r.value() - 100)
        self.canvas.set_points(
            CurvePoint(self.sp_low_t.value(), self.sp_low_r.value()),
            CurvePoint(self.sp_high_t.value(), self.sp_high_r.value()),
        )

    def _apply(self) -> None:
        low, high = self.canvas.points()
        if not (low.temp < high.temp < self.sp_max_t.value()):
            QMessageBox.warning(self, "Valori non validi",
                                "Le soglie devono crescere: low < high < max.")
            return
        cfg = MbpfanConfig(
            low_temp=low.temp,
            high_temp=high.temp,
            max_temp=self.sp_max_t.value(),
            polling_interval=self.sp_poll.value(),
            min_fan1_speed=low.rpm,
            max_fan1_speed=high.rpm,
        )
        ok, msg = mbpfan_ctrl.write_config(cfg)
        if not ok:
            QMessageBox.critical(self, "Errore", f"Scrittura config fallita:\n{msg}")
            return
        ok, msg = mbpfan_ctrl.restart_service()
        if not ok:
            QMessageBox.warning(self, "Servizio non riavviato",
                                f"Config scritta ma riavvio fallito:\n{msg}")
            self.accept(); return
        QMessageBox.information(self, "Fatto",
                                "Curva applicata e mbpfan riavviato.")
        self.accept()
