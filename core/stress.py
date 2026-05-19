"""
CPU stress test wrapper. Uses stress-ng if available, else falls back to a
pure-Python CPU burner. Runs in a background QProcess so the UI stays
responsive and we can interrupt it.
"""
from __future__ import annotations

import os
import shutil
from typing import Optional

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


class StressTest(QObject):
    """Manages a stress-ng (or fallback) process with elapsed/progress signals."""
    started_at = Signal(int)              # duration_seconds
    progress = Signal(int, int)           # elapsed, total
    finished = Signal(bool, str)          # ok, message

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._proc: Optional[QProcess] = None
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._on_tick)
        self._elapsed_ms = 0
        self._duration_s = 0
        self._method: str = ""

    @staticmethod
    def has_stress_ng() -> bool:
        return shutil.which("stress-ng") is not None

    @staticmethod
    def has_stress() -> bool:
        return shutil.which("stress") is not None

    def running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning

    def start(self, duration_seconds: int) -> bool:
        if self.running():
            return False
        self._duration_s = duration_seconds
        self._elapsed_ms = 0
        cpu_count = os.cpu_count() or 2

        if self.has_stress_ng():
            self._method = "stress-ng"
            cmd = "stress-ng"
            args = ["--cpu", str(cpu_count),
                    "--timeout", f"{duration_seconds}s",
                    "--metrics-brief"]
        elif self.has_stress():
            self._method = "stress"
            cmd = "stress"
            args = ["--cpu", str(cpu_count),
                    "--timeout", f"{duration_seconds}s"]
        else:
            # Pure-Python fallback: forks N CPU-burning Python loops via a
            # small inline script. Less accurate but works without deps.
            # Children call prctl(PR_SET_NAME) so they show up in 'ps' and
            # the top-processes panel as "fresh-fan-manager" rather than "python3".
            self._method = "python-fallback"
            cmd = "python3"
            py_code = (
                "import os,time,sys,ctypes\n"
                "def _rename():\n"
                "  try:\n"
                "    libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
                "    name = b'fresh-fan-manager'\n"
                "    libc.prctl(15, name, 0, 0, 0)  # PR_SET_NAME=15\n"
                "  except Exception: pass\n"
                "_rename()\n"
                f"N={cpu_count}\n"
                f"END=time.time()+{duration_seconds}\n"
                "for _ in range(N-1):\n"
                "  if os.fork()==0:\n"
                "    _rename()\n"
                "    while time.time()<END:\n"
                "      x=0\n"
                "      for i in range(100000): x=(x*x+1)%99991\n"
                "    sys.exit(0)\n"
                "while time.time()<END:\n"
                "  x=0\n"
                "  for i in range(100000): x=(x*x+1)%99991\n"
            )
            args = ["-c", py_code]

        self._proc = QProcess(self)
        self._proc.setProgram(cmd)
        self._proc.setArguments(args)
        self._proc.finished.connect(self._on_proc_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)
        self._proc.start()
        if not self._proc.waitForStarted(2000):
            self.finished.emit(False, f"Impossibile avviare {cmd}")
            self._proc = None
            return False

        self._timer.start()
        self.started_at.emit(duration_seconds)
        return True

    def stop(self) -> None:
        if self._proc is None:
            return
        self._timer.stop()
        if self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.terminate()
            if not self._proc.waitForFinished(2000):
                self._proc.kill()
        self._proc = None

    def method(self) -> str:
        return self._method

    def _on_tick(self) -> None:
        self._elapsed_ms += self._timer.interval()
        elapsed_s = min(self._duration_s, self._elapsed_ms // 1000)
        self.progress.emit(int(elapsed_s), self._duration_s)
        if elapsed_s >= self._duration_s:
            self._timer.stop()

    def _on_proc_finished(self, exit_code: int, _status) -> None:
        self._timer.stop()
        ok = exit_code == 0
        msg = f"Test completato ({self._method}, exit={exit_code})"
        self._proc = None
        self.finished.emit(ok, msg)

    def _on_proc_error(self, _err) -> None:
        self._timer.stop()
        msg = f"Errore esecuzione {self._method}"
        self._proc = None
        self.finished.emit(False, msg)
