"""System-level actions that may require privileges via the helper."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

HELPER_BIN = "/usr/local/bin/macfan-helper"


def drop_caches() -> tuple[bool, str]:
    """Drop pagecache + dentries + inodes (Linux drop_caches=3)."""
    if not Path(HELPER_BIN).exists():
        return False, "Helper non installato"
    try:
        r = subprocess.run(
            ["pkexec", HELPER_BIN, "drop-caches"],
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


def _apt_cache_size() -> int:
    return _du_path(Path("/var/cache/apt/archives"))


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
    return [
        CleanupTarget("drop_caches", "Cache kernel (drop_caches)",
                      "Buffer/cache kernel — equivalente al bottone 'Libera RAM'.",
                      0, True),
        CleanupTarget("journal", "Log di systemd (journalctl)",
                      "Mantiene solo gli ultimi 100 MB di log di sistema.",
                      _journal_size(), True),
        CleanupTarget("apt", "Cache pacchetti apt",
                      "/var/cache/apt/archives — file .deb scaricati.",
                      _apt_cache_size(), True),
        CleanupTarget("thumbnails", "Thumbnail",
                      "~/.cache/thumbnails — miniature dei file manager.",
                      _thumbnail_cache_size(), False),
        CleanupTarget("user_cache", "Cache utente (~/.cache)",
                      "Cache applicazioni utente (escluse thumbnail).",
                      _user_cache_size(), False),
        CleanupTarget("trash", "Cestino",
                      "~/.local/share/Trash — file nel cestino.",
                      _trash_size(), False),
    ]


def run_cleanup(keys: list[str]) -> tuple[bool, str, int]:
    if not keys:
        return False, "Nessuna voce selezionata", 0
    if not Path(HELPER_BIN).exists():
        return False, "Helper non installato", 0
    before = {}
    if "journal" in keys: before["journal"] = _journal_size()
    if "apt" in keys: before["apt"] = _apt_cache_size()
    if "thumbnails" in keys: before["thumbnails"] = _thumbnail_cache_size()
    if "user_cache" in keys: before["user_cache"] = _user_cache_size()
    if "trash" in keys: before["trash"] = _trash_size()
    try:
        args = ["pkexec", HELPER_BIN, "cleanup"] + keys
        r = subprocess.run(args, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return False, (r.stdout + r.stderr).strip(), 0
    except Exception as e:
        return False, str(e), 0
    freed = 0
    if "journal" in keys: freed += max(0, before["journal"] - _journal_size())
    if "apt" in keys: freed += max(0, before["apt"] - _apt_cache_size())
    if "thumbnails" in keys: freed += max(0, before["thumbnails"] - _thumbnail_cache_size())
    if "user_cache" in keys: freed += max(0, before["user_cache"] - _user_cache_size())
    if "trash" in keys: freed += max(0, before["trash"] - _trash_size())
    return True, "ok", freed
