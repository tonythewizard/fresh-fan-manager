"""
Sensor reading layer for MacBookAir7,2 (Early 2015) on Parrot OS.

All reads are non-blocking and fail-safe: if a sensor file is missing, the
field returns None and the UI handles it.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import psutil

SMC_PATH = Path("/sys/devices/platform/applesmc.768")
THERMAL_PATH = Path("/sys/class/thermal")
DRM_PATH = Path("/sys/class/drm")
BATTERY_PATH = Path("/sys/class/power_supply/BAT0")
CPUFREQ_PATH = Path("/sys/devices/system/cpu/cpu0/cpufreq")


@dataclass
class FanInfo:
    index: int
    label: str
    rpm: int
    min_rpm: int
    max_rpm: int
    manual: bool = False

    @property
    def percent(self) -> float:
        rng = max(1, self.max_rpm - self.min_rpm)
        return max(0.0, min(100.0, (self.rpm - self.min_rpm) / rng * 100.0))


@dataclass
class BatteryInfo:
    percent: float
    plugged: bool
    seconds_left: Optional[int]  # None if charging or unknown
    temp_c: Optional[float]
    voltage_v: Optional[float]
    current_a: Optional[float]
    cycle_count: Optional[int] = None
    energy_full_wh: Optional[float] = None
    energy_full_design_wh: Optional[float] = None
    health_percent: Optional[float] = None  # full / full_design


@dataclass
class ThrottleInfo:
    """Per-core thermal/power throttle counters from /sys/devices/system/cpu."""
    package_throttle_count: Optional[int]
    core_throttle_count: Optional[int]
    is_throttling: bool      # delta since last poll > 0
    last_seen_ago_s: Optional[float]  # seconds since the last throttle event


@dataclass
class DiskInfo:
    """SMART-derived info for the primary disk (best-effort, no smartctl needed)."""
    device: str
    model: Optional[str]
    temp_c: Optional[float]
    hours_on: Optional[int]
    power_cycles: Optional[int]
    health: Optional[str]    # "OK" / "FAIL" / None if unknown


@dataclass
class GpuInfo:
    cur_freq_mhz: Optional[int]
    max_freq_mhz: Optional[int]
    busy_percent: Optional[float]


@dataclass
class MemoryInfo:
    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent: float
    swap_total_bytes: int
    swap_used_bytes: int
    swap_percent: float


@dataclass
class TopProcess:
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    memory_rss_bytes: int


@dataclass
class Snapshot:
    """One sample of the entire system state."""
    timestamp: float
    cpu_temp_c: Optional[float]            # max core temp
    cpu_pkg_temp_c: Optional[float]        # package temp
    cpu_core_temps: list[float] = field(default_factory=list)
    cpu_percent_total: float = 0.0
    cpu_percent_per_core: list[float] = field(default_factory=list)
    cpu_freq_mhz: Optional[float] = None
    cpu_freq_max_mhz: Optional[float] = None
    fans: list[FanInfo] = field(default_factory=list)
    gpu: Optional[GpuInfo] = None
    battery: Optional[BatteryInfo] = None
    memory: Optional[MemoryInfo] = None
    top_processes: list[TopProcess] = field(default_factory=list)
    extra_temps: dict[str, float] = field(default_factory=dict)
    throttle: Optional[ThrottleInfo] = None
    disk: Optional[DiskInfo] = None

    def gpu_temp(self) -> Optional[float]:
        """GPU temp from any available SMC label."""
        for k in ("GPU Core", "GPU", "GPU Heatsink", "GPU Proximity",
                  "TCGC", "TG0D", "TG0H", "TG0P", "TG1H"):
            if k in self.extra_temps:
                return self.extra_temps[k]
        return None


def _read_int(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def _read_str(path: Path) -> Optional[str]:
    try:
        return path.read_text().strip()
    except Exception:
        return None


def _read_float_milli(path: Path) -> Optional[float]:
    """Read a millidegree/millivolt value and return it as a normal float."""
    v = _read_int(path)
    return v / 1000.0 if v is not None else None


# ---------------------------------------------------------------------------
# Fans
# ---------------------------------------------------------------------------

def read_fans() -> list[FanInfo]:
    fans: list[FanInfo] = []
    if not SMC_PATH.exists():
        return fans
    for input_file in sorted(SMC_PATH.glob("fan*_input")):
        # fan1_input -> index 1
        name = input_file.name
        try:
            idx = int(name.replace("fan", "").replace("_input", ""))
        except ValueError:
            continue
        rpm = _read_int(input_file) or 0
        label = _read_str(SMC_PATH / f"fan{idx}_label") or f"Fan {idx}"
        mn = _read_int(SMC_PATH / f"fan{idx}_min") or 0
        mx = _read_int(SMC_PATH / f"fan{idx}_max") or 6500
        manual = bool(_read_int(SMC_PATH / f"fan{idx}_manual") or 0)
        fans.append(FanInfo(index=idx, label=label, rpm=rpm, min_rpm=mn, max_rpm=mx, manual=manual))
    return fans


# ---------------------------------------------------------------------------
# CPU temps (coretemp via hwmon)
# ---------------------------------------------------------------------------

def _find_coretemp_hwmon() -> Optional[Path]:
    for hw in Path("/sys/class/hwmon").glob("hwmon*"):
        name = _read_str(hw / "name")
        if name == "coretemp":
            return hw
    return None


def read_cpu_temps() -> tuple[Optional[float], Optional[float], list[float]]:
    """Returns (max_core_temp, pkg_temp, [core_temps])."""
    hw = _find_coretemp_hwmon()
    if hw is None:
        return None, None, []
    pkg_temp: Optional[float] = None
    core_temps: list[float] = []
    for temp_input in sorted(hw.glob("temp*_input")):
        idx = temp_input.name.replace("temp", "").replace("_input", "")
        label = _read_str(hw / f"temp{idx}_label") or ""
        val = _read_float_milli(temp_input)
        if val is None:
            continue
        if "Package" in label:
            pkg_temp = val
        elif "Core" in label:
            core_temps.append(val)
    max_core = max(core_temps) if core_temps else pkg_temp
    return max_core, pkg_temp, core_temps


def read_smc_extra_temps() -> dict[str, float]:
    """All SMC temps, keyed by friendly name when known and also by raw label.
    The kernel's applesmc module may expose either the 4-char SMC key (e.g. 'TB0T')
    or a human-readable label depending on version — we accept both."""
    label_map = {
        # SMC keys
        "TCGC": "GPU Core", "TG0D": "GPU", "TG0H": "GPU Heatsink",
        "TG0P": "GPU Proximity", "TG1H": "GPU Heatsink",
        "TM0P": "Memory", "TB0T": "Battery", "TW0P": "WiFi",
        "Th1H": "Heatpipe", "TPCD": "PCH", "TC0P": "CPU Proximity",
        "TC0D": "CPU Die", "TC0E": "CPU", "TC0F": "CPU",
        # Human-readable variants used on newer kernels
        "GPU Core": "GPU Core", "GPU": "GPU",
        "GPU Heatsink": "GPU Heatsink", "GPU Proximity": "GPU Proximity",
        "Memory bank A": "Memory", "Memory": "Memory",
        "Battery": "Battery", "Heatpipe": "Heatpipe",
        "PCH": "PCH", "CPU Proximity": "CPU Proximity",
        "CPU Die": "CPU Die", "CPU": "CPU",
    }
    out: dict[str, float] = {}
    if not SMC_PATH.exists():
        return out
    # Search both the new hwmon subdir and the direct attrs (older kernels)
    search_paths = []
    smc_hwmon = SMC_PATH / "hwmon"
    if smc_hwmon.exists():
        search_paths.extend(smc_hwmon.glob("hwmon*"))
    search_paths.append(SMC_PATH)  # fallback to direct attrs
    for hw in search_paths:
        for temp_input in hw.glob("temp*_input"):
            idx = temp_input.name.replace("temp", "").replace("_input", "")
            label = _read_str(hw / f"temp{idx}_label") or ""
            val = _read_float_milli(temp_input)
            if val is None or not (-20 < val < 130):
                continue
            # Always store under the raw label (whatever it is)
            if label:
                out[label] = val
            # Also store under the friendly key when known
            friendly = label_map.get(label)
            if friendly:
                out.setdefault(friendly, val)
    return out


def _get_temp(extras: dict[str, float], *keys: str) -> Optional[float]:
    """Try each key in order and return the first match."""
    for k in keys:
        if k in extras:
            return extras[k]
    return None


# ---------------------------------------------------------------------------
# CPU load/freq
# ---------------------------------------------------------------------------

def read_cpu_load() -> tuple[float, list[float]]:
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    total = sum(per_core) / max(1, len(per_core))
    return total, per_core


def read_cpu_freq() -> tuple[Optional[float], Optional[float]]:
    try:
        f = psutil.cpu_freq()
        if f:
            return f.current, f.max
    except Exception:
        pass
    return None, None


# ---------------------------------------------------------------------------
# GPU (Intel HD Graphics 6000)
# ---------------------------------------------------------------------------

_last_gpu_busy_ns: Optional[int] = None
_last_gpu_busy_time: Optional[float] = None
_cached_intel_card: Optional[Path] = None


def _find_intel_card() -> Optional[Path]:
    """Locate the Intel iGPU sysfs directory. Cards may be card0, card1, etc.
    on modern kernels with DRM display device split."""
    global _cached_intel_card
    if _cached_intel_card is not None and _cached_intel_card.exists():
        return _cached_intel_card
    candidates: list[Path] = []
    for card_path in sorted(DRM_PATH.glob("card*")):
        if not card_path.is_dir() or "-" in card_path.name:
            continue
        # Need an Intel device (vendor 0x8086) with i915 driver
        vendor_file = card_path / "device" / "vendor"
        try:
            if vendor_file.exists() and vendor_file.read_text().strip() == "0x8086":
                candidates.append(card_path)
        except Exception:
            continue
    # Prefer one that has gt_cur_freq_mhz (the render device, not display-only)
    for c in candidates:
        if (c / "gt_cur_freq_mhz").exists():
            _cached_intel_card = c
            return c
    if candidates:
        _cached_intel_card = candidates[0]
        return candidates[0]
    return None


def read_gpu() -> GpuInfo:
    global _last_gpu_busy_ns, _last_gpu_busy_time
    card = _find_intel_card()
    if card is None:
        return GpuInfo(cur_freq_mhz=None, max_freq_mhz=None, busy_percent=None)
    cur = _read_int(card / "gt_cur_freq_mhz")
    mx = _read_int(card / "gt_max_freq_mhz")

    busy_pct: Optional[float] = None
    # Method 1: per-engine busy counters (i915, kernel >= 5.13)
    busy_files = list(card.glob("engine/*/busy"))
    if busy_files:
        total_ns = 0
        any_read = False
        for bf in busy_files:
            v = _read_int(bf)
            if v is not None:
                total_ns += v
                any_read = True
        if any_read:
            now = time.monotonic()
            if _last_gpu_busy_ns is not None and _last_gpu_busy_time is not None:
                dt_ns = (now - _last_gpu_busy_time) * 1e9
                db = total_ns - _last_gpu_busy_ns
                if dt_ns > 0 and db >= 0:
                    # Average across engines (cap at 100% per-engine sum)
                    busy_pct = min(100.0, max(0.0, db / dt_ns * 100.0 / max(1, len(busy_files))))
            _last_gpu_busy_ns = total_ns
            _last_gpu_busy_time = now

    return GpuInfo(cur_freq_mhz=cur, max_freq_mhz=mx, busy_percent=busy_pct)


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------

def read_battery() -> Optional[BatteryInfo]:
    if not BATTERY_PATH.exists():
        return None
    try:
        bat = psutil.sensors_battery()
        if bat is None:
            return None
        seconds = None
        if bat.secsleft is not None and bat.secsleft >= 0:
            seconds = int(bat.secsleft)

        # Extra info from sysfs directly
        voltage = _read_float_milli(BATTERY_PATH / "voltage_now")
        if voltage is not None:
            voltage = voltage / 1000.0  # microvolt -> volt
        current = _read_float_milli(BATTERY_PATH / "current_now")
        if current is not None:
            current = current / 1000.0  # microamp -> amp

        # Battery temp: try multiple sources
        temp_c: Optional[float] = None
        # 1) /sys/class/power_supply/BAT0/temp (tenths of °C on most kernels)
        psup_temp = _read_int(BATTERY_PATH / "temp")
        if psup_temp is not None:
            # Could be tenths of °C (typical) or millidegrees on some kernels
            if 100 < psup_temp < 1000:
                temp_c = psup_temp / 10.0
            elif 10000 < psup_temp < 100000:
                temp_c = psup_temp / 1000.0
        # 2) Fall back to SMC (TB0T or "Battery" label)
        if temp_c is None:
            extras = read_smc_extra_temps()
            temp_c = _get_temp(extras, "Battery", "TB0T")

        # Battery health & cycle count
        cycle = _read_int(BATTERY_PATH / "cycle_count")
        ef = _read_int(BATTERY_PATH / "energy_full")
        efd = _read_int(BATTERY_PATH / "energy_full_design")
        # Some kernels use charge_full instead of energy_full (units differ but ratio still valid)
        if ef is None:
            ef = _read_int(BATTERY_PATH / "charge_full")
        if efd is None:
            efd = _read_int(BATTERY_PATH / "charge_full_design")
        energy_full_wh = ef / 1_000_000.0 if ef else None
        energy_full_design_wh = efd / 1_000_000.0 if efd else None
        health = None
        if ef and efd and efd > 0:
            health = min(100.0, ef / efd * 100.0)

        return BatteryInfo(
            percent=bat.percent,
            plugged=bat.power_plugged,
            seconds_left=seconds,
            temp_c=temp_c,
            voltage_v=voltage,
            current_a=current,
            cycle_count=cycle,
            energy_full_wh=energy_full_wh,
            energy_full_design_wh=energy_full_design_wh,
            health_percent=health,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

def read_memory() -> Optional[MemoryInfo]:
    try:
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        return MemoryInfo(
            total_bytes=vm.total,
            used_bytes=vm.used,
            available_bytes=vm.available,
            percent=vm.percent,
            swap_total_bytes=sw.total,
            swap_used_bytes=sw.used,
            swap_percent=sw.percent,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Top processes
# ---------------------------------------------------------------------------

# We keep psutil.Process objects across ticks so cpu_percent() returns the
# delta since the previous call (which is what we actually want).
_process_cache: dict[int, "psutil.Process"] = {}
_top_proc_warmed_up: bool = False


def read_top_processes(limit: int = 5) -> list[TopProcess]:
    """Top N processes by CPU%. First call is a warmup (returns []), subsequent
    calls return the deltas. Use periodically (every ~2s)."""
    global _top_proc_warmed_up
    import psutil as _ps
    live_pids: set[int] = set()
    results: list[tuple[float, TopProcess]] = []

    for proc in _ps.process_iter(['pid', 'name']):
        try:
            pid = proc.info['pid']
            live_pids.add(pid)
            cached = _process_cache.get(pid)
            if cached is None or cached.pid != pid:
                cached = _ps.Process(pid)
                _process_cache[pid] = cached
                cached.cpu_percent(interval=None)  # prime
                continue
            cp = cached.cpu_percent(interval=None)
            with cached.oneshot():
                mp = cached.memory_percent()
                rss = cached.memory_info().rss
                name = proc.info['name'] or "?"
            results.append((cp, TopProcess(
                pid=pid, name=name, cpu_percent=cp,
                memory_percent=mp, memory_rss_bytes=rss,
            )))
        except (_ps.NoSuchProcess, _ps.AccessDenied, _ps.ZombieProcess):
            continue
        except Exception:
            continue

    # Evict stale cache entries
    for pid in list(_process_cache.keys()):
        if pid not in live_pids:
            _process_cache.pop(pid, None)

    if not _top_proc_warmed_up:
        _top_proc_warmed_up = True
        return []

    results.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in results[:limit]]


_last_throttle_total: Optional[int] = None
_last_throttle_time: Optional[float] = None
_last_throttle_event: Optional[float] = None


def read_throttle() -> ThrottleInfo:
    """Sum thermal_throttle/{package_,core_}throttle_count across all CPUs.
    Detect throttling by monitoring the delta between polls."""
    global _last_throttle_total, _last_throttle_time, _last_throttle_event
    pkg_total = 0
    pkg_found = False
    core_total = 0
    core_found = False
    base = Path("/sys/devices/system/cpu")
    for cpu in base.glob("cpu[0-9]*"):
        th = cpu / "thermal_throttle"
        if not th.is_dir():
            continue
        p = _read_int(th / "package_throttle_count")
        if p is not None:
            pkg_total += p
            pkg_found = True
        c = _read_int(th / "core_throttle_count")
        if c is not None:
            core_total += c
            core_found = True
    grand_total = (pkg_total if pkg_found else 0) + (core_total if core_found else 0)
    now = time.monotonic()
    is_now = False
    if _last_throttle_total is not None and grand_total > _last_throttle_total:
        is_now = True
        _last_throttle_event = now
    _last_throttle_total = grand_total
    _last_throttle_time = now
    last_ago = (now - _last_throttle_event) if _last_throttle_event is not None else None
    return ThrottleInfo(
        package_throttle_count=pkg_total if pkg_found else None,
        core_throttle_count=core_total if core_found else None,
        is_throttling=is_now,
        last_seen_ago_s=last_ago,
    )


def _detect_primary_disk() -> Optional[str]:
    """Find the device for /. Returns something like 'sda' or 'nvme0n1'."""
    try:
        # findmnt is in util-linux on Parrot
        r = subprocess.run(
            ["findmnt", "-no", "SOURCE", "/"],
            capture_output=True, text=True, timeout=2,
        )
        src = r.stdout.strip()
        if not src:
            return None
        # Strip /dev/ and any partition number to get the parent device
        name = src.replace("/dev/", "")
        # Handle nvme0n1p3 -> nvme0n1, sda3 -> sda
        if name.startswith("nvme"):
            # nvme0n1p2 -> nvme0n1
            import re as _re
            m = _re.match(r"(nvme\d+n\d+)", name)
            return m.group(1) if m else name
        # sda1 -> sda
        return name.rstrip("0123456789")
    except Exception:
        return None


def read_disk() -> Optional[DiskInfo]:
    """Best-effort disk info. Reads from /sys/block/<dev>/device when possible.
    SMART details require smartctl (suggested as optional install) and are run
    in a non-blocking way with a tight timeout."""
    dev = _detect_primary_disk()
    if not dev:
        return None
    sysblock = Path(f"/sys/block/{dev}")
    model = _read_str(sysblock / "device" / "model")
    if model:
        model = model.strip()
    temp_c: Optional[float] = None
    hours_on: Optional[int] = None
    power_cycles: Optional[int] = None
    health: Optional[str] = None
    # Try smartctl in JSON mode (no privileges needed for SATA/NVMe info reads on most kernels)
    smartctl = shutil.which("smartctl")
    if smartctl:
        try:
            r = subprocess.run(
                [smartctl, "-A", "-H", "-j", f"/dev/{dev}"],
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode in (0, 4):  # 4 = checksum warnings, still readable
                import json as _json
                data = _json.loads(r.stdout or "{}")
                # Temperature
                temp = (data.get("temperature") or {}).get("current")
                if isinstance(temp, (int, float)):
                    temp_c = float(temp)
                # Power on hours
                poh = (data.get("power_on_time") or {}).get("hours")
                if isinstance(poh, int):
                    hours_on = poh
                # Power cycles
                pc = data.get("power_cycle_count")
                if isinstance(pc, int):
                    power_cycles = pc
                # Health
                passed = (data.get("smart_status") or {}).get("passed")
                if isinstance(passed, bool):
                    health = "OK" if passed else "FAIL"
                # Some drives expose temp in ata_smart_attributes
                if temp_c is None:
                    attrs = (data.get("ata_smart_attributes") or {}).get("table", [])
                    for a in attrs:
                        if a.get("id") in (190, 194):
                            raw = a.get("raw", {}).get("value")
                            if isinstance(raw, int) and 10 < raw < 100:
                                temp_c = float(raw)
                                break
        except Exception:
            pass
    # Fallback: hwmon may expose drive temp on some NVMe drives
    if temp_c is None:
        for hw in Path("/sys/class/hwmon").glob("hwmon*"):
            name = _read_str(hw / "name") or ""
            if "nvme" in name.lower() and dev.startswith("nvme"):
                t = _read_float_milli(hw / "temp1_input")
                if t is not None:
                    temp_c = t
                    break
    return DiskInfo(
        device=f"/dev/{dev}",
        model=model,
        temp_c=temp_c,
        hours_on=hours_on,
        power_cycles=power_cycles,
        health=health,
    )


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# Top-level snapshot
# ---------------------------------------------------------------------------

def snapshot(include_top_processes: bool = True,
             top_processes_limit: int = 5,
             include_disk: bool = False) -> Snapshot:
    """Take a full system snapshot.
    `include_disk` is opt-in because reading SMART can be slow on some drives;
    callers (e.g. main window) should refresh it on a slower timer."""
    max_t, pkg_t, cores = read_cpu_temps()
    load_total, load_per = read_cpu_load()
    f_cur, f_max = read_cpu_freq()
    return Snapshot(
        timestamp=time.time(),
        cpu_temp_c=max_t,
        cpu_pkg_temp_c=pkg_t,
        cpu_core_temps=cores,
        cpu_percent_total=load_total,
        cpu_percent_per_core=load_per,
        cpu_freq_mhz=f_cur,
        cpu_freq_max_mhz=f_max,
        fans=read_fans(),
        gpu=read_gpu(),
        battery=read_battery(),
        memory=read_memory(),
        top_processes=read_top_processes(top_processes_limit) if include_top_processes else [],
        extra_temps=read_smc_extra_temps(),
        throttle=read_throttle(),
        disk=read_disk() if include_disk else None,
    )


def format_seconds(s: Optional[int]) -> str:
    if s is None:
        return "—"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h{m:02d}m" if h else f"{m}m"
