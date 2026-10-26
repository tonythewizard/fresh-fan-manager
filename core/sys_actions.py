# SPDX-License-Identifier: GPL-3.0-or-later
"""System-level actions that may require privileges via the helper."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.i18n import tr


def find_helper_bin() -> str:
    for p in ("/usr/local/bin/freshfan-helper", "/usr/local/bin/macfan-helper", "/usr/bin/freshfan-helper"):
        if Path(p).exists():
            return p
    return "/usr/local/bin/freshfan-helper"


HELPER_BIN = find_helper_bin()


def drop_caches() -> tuple[bool, str]:
    """Drop pagecache + dentries + inodes (Linux drop_caches=3)."""
    helper = find_helper_bin()
    if not Path(helper).exists():
        return False, "Helper non installato"
    try:
        r = subprocess.run(
            ["pkexec", helper, "drop-caches"],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


@dataclass
class CleanupTarget:
    key: str
    label: str
    description: str
    size_bytes: int
    needs_root: bool


def _du_path(p: Path) -> int:
    if not p.exists():
        return 0
    try:
        r = subprocess.run(["du", "-sb", str(p)],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return int(r.stdout.split()[0])
    except Exception:
        pass
    total = 0
    try:
        for root, _, files in os.walk(p, onerror=lambda e: None):
            for f in files:
                try:
                    total += (Path(root) / f).stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return total


def _journal_size() -> int:
    try:
        r = subprocess.run(["journalctl", "--disk-usage"],
                           capture_output=True, text=True, timeout=5)
        m = re.search(r"([\d.]+)\s*([KMGT])", r.stdout)
        if not m:
            return 0
        val = float(m.group(1))
        mult = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}[m.group(2)]
        return int(val * mult)
    except Exception:
        return 0


def _pkg_cache_info() -> tuple[int, str, str]:
    if shutil.which("pacman"):
        p = Path("/var/cache/pacman/pkg")
        return _du_path(p), "Pacman Cache", f"{p} — pacman downloaded package archives."
    elif shutil.which("apt-get"):
        p = Path("/var/cache/apt/archives")
        return _du_path(p), "APT Cache", f"{p} — downloaded .deb package archives."
    elif shutil.which("dnf"):
        p = Path("/var/cache/dnf")
        return _du_path(p), "DNF Cache", f"{p} — dnf package cache."
    return 0, tr("target_pkg_cache"), tr("desc_pkg_cache")


def _thumbnail_cache_size() -> int:
    return _du_path(Path.home() / ".cache" / "thumbnails")


def _trash_size() -> int:
    return _du_path(Path.home() / ".local" / "share" / "Trash")


def _user_cache_size() -> int:
    cache = Path.home() / ".cache"
    total = _du_path(cache)
    thumb = _du_path(cache / "thumbnails")
    return max(0, total - thumb)


def enumerate_cleanup_targets() -> list[CleanupTarget]:
    pkg_size, pkg_label, pkg_desc = _pkg_cache_info()
    return [
        CleanupTarget("drop_caches", tr("target_drop_caches"),
                      tr("desc_drop_caches"),
                      0, True),
        CleanupTarget("journal", tr("target_journal"),
                      tr("desc_journal"),
                      _journal_size(), True),
        CleanupTarget("pkg_cache", pkg_label,
                      pkg_desc,
                      pkg_size, True),
        CleanupTarget("thumbnails", tr("target_thumbnails"),
                      tr("desc_thumbnails"),
                      _thumbnail_cache_size(), False),
        CleanupTarget("user_cache", tr("target_user_cache"),
                      tr("desc_user_cache"),
                      _user_cache_size(), False),
        CleanupTarget("trash", tr("target_trash"),
                      tr("desc_trash"),
                      _trash_size(), False),
    ]


def _clean_user_directory(directory: Path, exclude: tuple[str, ...] = ()) -> None:
    # Run with the desktop user's privileges; never ask a root helper to walk
    # a user-controlled directory or follow its symlinks.
    if directory.is_symlink():
        raise ValueError(f"Refusing symlink cleanup root: {directory}")
    if not directory.exists():
        return
    for child in directory.iterdir():
        if child.name in exclude:
            continue
        if child.is_symlink() or not child.is_dir():
            child.unlink()
        else:
            shutil.rmtree(child)


def run_cleanup(keys: list[str]) -> tuple[bool, str, int]:
    system_keys = {"drop_caches", "journal", "pkg_cache", "apt"}
    user_keys = {"thumbnails", "user_cache", "trash"}
    if not keys or any(key not in system_keys | user_keys for key in keys):
        return False, "Invalid cleanup target", 0
    targets = {t.key: t for t in enumerate_cleanup_targets()}
    selected = set(keys)
    if "apt" in selected:
        selected.remove("apt")
        selected.add("pkg_cache")
    before = sum(targets[k].size_bytes for k in selected)
    try:
        privileged = sorted(selected & system_keys)
        if privileged:
            helper = find_helper_bin()
            if not Path(helper).exists():
                return False, "Helper not installed", 0
            result = subprocess.run(["pkexec", helper, "cleanup"] + privileged,
                                    capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return False, (result.stdout + result.stderr).strip(), 0
        home = Path.home()
        if "thumbnails" in selected:
            _clean_user_directory(home / ".cache/thumbnails")
        if "user_cache" in selected:
            _clean_user_directory(home / ".cache", exclude=("thumbnails", "fresh-fan-manager"))
        if "trash" in selected:
            _clean_user_directory(home / ".local/share/Trash")
        after = {t.key: t for t in enumerate_cleanup_targets()}
        freed = max(0, before - sum(after[k].size_bytes for k in selected))
        return True, "ok", freed
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return False, str(exc), 0


def set_turbo(on: bool) -> tuple[bool, str]:
    helper = find_helper_bin()
    if not Path(helper).exists():
        return False, "Helper not found"
    try:
        r = subprocess.run(["pkexec", helper, "set-turbo", "1" if on else "0"],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def set_brightness(percent: int) -> tuple[bool, str]:
    helper = find_helper_bin()
    if not Path(helper).exists():
        return False, "Helper not found"
    try:
        pct = max(1, min(100, int(percent)))
        r = subprocess.run(["pkexec", helper, "set-brightness", str(pct)],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def set_audio_volume(percent: int) -> tuple[bool, str]:
    """Set master audio volume unprivileged via wpctl or pactl."""
    pct = max(0, min(150, int(percent)))
    if shutil.which("wpctl"):
        try:
            val_f = f"{pct / 100.0:.2f}"
            r = subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", val_f],
                               capture_output=True, text=True, timeout=3)
            return r.returncode == 0, r.stdout.strip()
        except Exception as e:
            return False, str(e)
    elif shutil.which("pactl"):
        try:
            r = subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"],
                               capture_output=True, text=True, timeout=3)
            return r.returncode == 0, r.stdout.strip()
        except Exception as e:
            return False, str(e)
    return False, "No audio controller found"


def toggle_audio_mute() -> tuple[bool, str]:
    """Toggle audio mute unprivileged via wpctl or pactl."""
    if shutil.which("wpctl"):
        try:
            r = subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
                               capture_output=True, text=True, timeout=3)
            return r.returncode == 0, r.stdout.strip()
        except Exception as e:
            return False, str(e)
    elif shutil.which("pactl"):
        try:
            r = subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                               capture_output=True, text=True, timeout=3)
            return r.returncode == 0, r.stdout.strip()
        except Exception as e:
            return False, str(e)
    return False, "No audio controller found"
