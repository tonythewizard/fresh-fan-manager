# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded CPU workload with process-group cancellation and elapsed signals."""
from __future__ import annotations

import os
import shutil
import signal
import sys
import time
from typing import Optional
from PySide6.QtCore import QObject, QProcess, QTimer, Signal


class StressTest(QObject):
    started_at = Signal(int)
    progress = Signal(int, int)
    finished = Signal(bool, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._proc = None
        self._process_group = None
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._on_tick)
        self._duration_s = 0
        self._started = 0.0
        self._method = ''
        self._stopping = False

    @staticmethod
    def has_stress_ng():
        return shutil.which('stress-ng') is not None

    @staticmethod
    def has_stress():
        return shutil.which('stress') is not None

    def running(self):
        return self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning

    def start(self, duration_seconds: int) -> bool:
        if self.running() or not 1 <= duration_seconds <= 90:
            return False
        self._duration_s = duration_seconds
        self._stopping = False
        count = os.cpu_count() or 2
        if self.has_stress_ng():
            self._method = 'stress-ng'
            program, args = 'stress-ng', ['--cpu', str(count), '--timeout', f'{duration_seconds}s', '--metrics-brief']
        elif self.has_stress():
            self._method = 'stress'
            program, args = 'stress', ['--cpu', str(count), '--timeout', f'{duration_seconds}s']
        else:
            self._method = 'python-fallback'
            program = sys.executable
            script = (
                'import os,time\n'
                f'end=time.monotonic()+{duration_seconds}\n'
                f'for _ in range({count}-1):\n'
                '  if os.fork()==0: break\n'
                'while time.monotonic()<end:\n'
                '  x=0\n'
                '  for i in range(10000): x=(x*x+1)%99991\n'
            )
            args = ['-c', script]
        proc = QProcess(self)
        self._proc = proc
        if hasattr(QProcess, 'UnixProcessFlag') and hasattr(QProcess.UnixProcessFlag, 'CreateNewSession'):
            params = QProcess.UnixProcessParameters()
            params.flags = QProcess.UnixProcessFlag.CreateNewSession
            proc.setUnixProcessParameters(params)
        elif shutil.which('setsid'):
            args, program = [program] + args, 'setsid'
        else:
            self._finish(proc, False, 'setsid is required for safe workload cancellation')
            return False
        proc.setProgram(program)
        proc.setArguments(args)
        proc.finished.connect(lambda code, status: self._on_finished(proc, code))
        proc.errorOccurred.connect(lambda error: self._on_error(proc, error))
        proc.start()
        if not proc.waitForStarted(2000):
            self._finish(proc, False, f'Cannot start {program}')
            return False
        self._process_group = int(proc.processId())
        self._started = time.monotonic()
        self._timer.start()
        self.started_at.emit(duration_seconds)
        return True

    @staticmethod
    def _signal_group(group, sig):
        if group:
            try:
                os.killpg(group, sig)
            except ProcessLookupError:
                pass

    def stop(self):
        proc, group = self._proc, self._process_group
        if proc is None:
            return
        self._stopping = True
        self._timer.stop()
        self._signal_group(group, signal.SIGTERM)
        proc.waitForFinished(1500)
        # A worker can outlive its parent, so always reap the rest of the group.
        self._signal_group(group, signal.SIGKILL)
        if self._proc is proc:
            proc.waitForFinished(1000)
            self._finish(proc, False, 'Stress test stopped')

    def method(self):
        return self._method

    def _on_tick(self):
        elapsed = min(self._duration_s, int(time.monotonic() - self._started))
        self.progress.emit(elapsed, self._duration_s)
        if elapsed >= self._duration_s:
            self.stop()  # Also bound workloads that fail to honor their timeout.

    def _on_finished(self, proc, code):
        if self._proc is not proc:
            return
        self._signal_group(self._process_group, signal.SIGKILL)
        self._finish(proc, code == 0 and not self._stopping,
                     'Stress test stopped' if self._stopping else f'Test completed ({self._method}, exit={code})')

    def _on_error(self, proc, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._finish(proc, False, f'Cannot start {self._method}')

    def _finish(self, proc, ok, message):
        if self._proc is not proc:
            return
        self._timer.stop()
        self._proc = None
        self._process_group = None
        proc.deleteLater()
        self.finished.emit(ok, message)
