# SPDX-License-Identifier: GPL-3.0-or-later
"""Release metadata validation, version comparison and update scheduling."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import urlsplit
from core.version import __version__

REPOSITORY = "tonythewizard/fresh-fan-manager"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_RESPONSE_BYTES = 512 * 1024


def stable_version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?", value)
    if not match:
        raise ValueError("Unsupported release version")
    return tuple(int(part or 0) for part in match.groups())


def trusted_release_url(value: str, download: bool = False) -> bool:
    url = urlsplit(value)
    prefix = f"/{REPOSITORY}/releases/" + ("download/" if download else "tag/")
    return (url.scheme == "https" and url.netloc == "github.com"
            and url.path.startswith(prefix) and not url.query and not url.fragment)


@dataclass(frozen=True)
class Release:
    tag: str
    notes: str
    url: str
    assets: tuple[tuple[str, str], ...]

    @property
    def newer(self) -> bool:
        return stable_version(self.tag) > stable_version(__version__)


def parse_release(data: dict) -> Release:
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        raise ValueError("No stable release available")
    tag = data.get("tag_name", "")
    stable_version(tag)
    url = data.get("html_url", "")
    if not trusted_release_url(url):
        raise ValueError("Unexpected release URL")
    assets = []
    for item in data.get("assets", []):
        name, target = item.get("name", ""), item.get("browser_download_url", "")
        if isinstance(name, str) and trusted_release_url(target, download=True):
            if name.endswith((".deb", ".rpm", ".pkg.tar.zst")):
                assets.append((name, target))
    notes = data.get("body") or ""
    if not isinstance(notes, str):
        raise ValueError("Invalid release notes")
    return Release(tag, notes, url, tuple(assets))


def check_due(interval_hours: int, last_attempt: float, now: float) -> bool:
    return interval_hours in (24, 168) and (now < last_attempt or now - last_attempt >= interval_hours * 3600)


def git_checkout() -> Path | None:
    root = Path(__file__).resolve().parent.parent
    return root if (root / ".git").exists() and (root / "tools/update_checkout.sh").is_file() else None
