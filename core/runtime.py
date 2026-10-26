# SPDX-License-Identifier: GPL-3.0-or-later
"""A per-user lease prevents the GUI and user daemon fighting over controls."""
import fcntl
import os
from pathlib import Path


class ControlLease:
    def __init__(self):
        self._file = None

    def acquire(self) -> bool:
        directory = Path(os.environ.get("XDG_RUNTIME_DIR") or Path.home() / ".cache/fresh-fan-manager")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(str(directory / "fresh-fan-manager.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self._file = os.fdopen(fd, "w")
        try:
            fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            self.release()
            return False

    def release(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
