"""
Read and switch CPU governor across all online cores.
Switching is routed through the pkexec helper.

User-facing the app exposes only three profiles:
    Saving       (powersave)
    Balanced     (schedutil > ondemand > conservative > ...)
    Performance  (performance)
The mapping is done here so the GUI doesn't have to deal with
kernel-driver-specific governor names.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

CPU_BASE = Path("/sys/devices/system/cpu")
HELPER_BIN = "/usr/local/bin/macfan-helper"

# Order of preference for what to use as "Balanced"
_BALANCED_PRIORITY = ("schedutil", "ondemand", "conservative", "userspace")


def _cpu_dirs() -> List[Path]:
    return sorted([p for p in CPU_BASE.glob("cpu[0-9]*") if (p / "cpufreq").exists()])


def current_governor() -> Optional[str]:
    """Return cpu0's governor (assumes uniform)."""
    p = CPU_BASE / "cpu0/cpufreq/scaling_governor"
    try:
        return p.read_text().strip()
    except Exception:
        return None


def available_governors() -> List[str]:
    p = CPU_BASE / "cpu0/cpufreq/scaling_available_governors"
    try:
        return p.read_text().strip().split()
    except Exception:
        return []


def resolve_balanced_governor() -> Optional[str]:
    """Pick the best 'balanced' governor available on this system."""
    avail = set(available_governors())
    if not avail:
        return None
    for g in _BALANCED_PRIORITY:
        if g in avail:
            return g
    # Fallback: anything that isn't performance/powersave
    for g in avail:
        if g not in ("performance", "powersave"):
            return g
    return None


def current_profile() -> str:
    """Return user-facing profile name based on the running governor."""
    g = current_governor()
    if g == "performance":
        return "Performance"
    if g == "powersave":
        return "Saving"
    return "Balanced"


def set_profile(profile: str) -> tuple[bool, str]:
    """Apply a user-facing profile (Saving / Balanced / Performance)."""
    avail = set(available_governors())
    if profile == "Saving":
        target = "powersave"
    elif profile == "Performance":
        target = "performance"
    elif profile == "Balanced":
        target = resolve_balanced_governor()
        if target is None:
            return False, "Nessun governor 'balanced' disponibile"
    else:
        return False, f"Profilo sconosciuto: {profile}"
    if target not in avail:
        return False, (f"Governor '{target}' non disponibile su questo kernel/driver. "
                       f"Disponibili: {', '.join(sorted(avail)) or '—'}")
    return set_governor(target)


def set_governor(name: str) -> tuple[bool, str]:
    if not Path(HELPER_BIN).exists():
        return False, "Helper missing"
    try:
        r = subprocess.run(
            ["pkexec", HELPER_BIN, "set-governor", name],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)
