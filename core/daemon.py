# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless thermal watchdog and optional AppleSMC preset controller."""
from __future__ import annotations

import signal
import threading
from core import config, sensors, mbpfan_ctrl
from core.logger import get_logger
from core.runtime import ControlLease


class HeadlessFanDaemon:
    def __init__(self, interval: float = 3.0):
        self.interval = max(0.5, interval)
        self.log = get_logger()
        self.settings = config.load()
        self._stop = threading.Event()
        self._last_rpm = None
        self._owned_fans: set[int] = set()
        self._safety_latched = False

    def _setup_signals(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: self.stop())

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> int:
        self._setup_signals()
        lease = ControlLease()
        if not lease.acquire():
            self.log.error("Another Fresh Fan Manager controller is already running.")
            return 1
        self.log.info("Fresh Fan Manager daemon started (backend=%s)", mbpfan_ctrl.get_backend())
        try:
            while not self._stop.is_set():
                try:
                    self._tick()
                except Exception:
                    self.log.exception("Daemon tick failed; restoring owned fans to automatic")
                    self._restore_owned()
                self._stop.wait(self.interval)
        finally:
            ok = self._restore_owned()
            lease.release()
        self.log.info("Fresh Fan Manager daemon stopped.")
        return 0 if ok else 1

    def _restore_owned(self) -> bool:
        ok_all = True
        for index in tuple(self._owned_fans):
            ok, message = mbpfan_ctrl.manual_off(index)
            if ok:
                self._owned_fans.discard(index)
            else:
                ok_all = False
                self.log.error("Could not restore fan %s to auto: %s", index, message)
        self._last_rpm = None
        return ok_all

    def _tick(self) -> None:
        self.settings = config.load()
        s = sensors.snapshot(include_top_processes=False, include_disk=False)
        temp = s.cpu_temp_c
        unsafe = temp is None or temp >= self.settings.manual_safety_temp_c
        if self.settings.manual_safety_enabled and unsafe:
            self._safety_latched = True
            self._owned_fans.update(f.index for f in s.fans if f.manual)
            self._restore_owned()
            return  # Never reapply a manual target after the safety trip.
        if self._safety_latched:
            # Hysteresis avoids toggling between auto/manual near the threshold.
            if temp is None or temp >= self.settings.manual_safety_temp_c - 5:
                return
            self._safety_latched = False
        if temp is None:
            self._restore_owned()
            return
        if mbpfan_ctrl.get_backend() != "applesmc" or not self.settings.active_preset:
            self._restore_owned()
            return
        cfg = mbpfan_ctrl.PRESETS.get(self.settings.active_preset)
        if cfg is None:
            self._restore_owned()
            return
        low, high = cfg.min_fan1_speed or 1500, cfg.max_fan1_speed or 6200
        ratio = max(0.0, min(1.0, (temp - cfg.low_temp) / max(1, cfg.max_temp - cfg.low_temp)))
        target = int(low + ratio * (high - low)) // 50 * 50
        if self._last_rpm is None or abs(target - self._last_rpm) >= 150:
            # Enable manual mode as well as setting target, then check the result.
            ok, message = mbpfan_ctrl.manual_on(target, 1)
            if ok:
                self._owned_fans.add(1)
                self._last_rpm = target
            else:
                self.log.error("Failed to apply target: %s", message)
