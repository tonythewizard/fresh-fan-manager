# SPDX-License-Identifier: GPL-3.0-or-later
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
class DmiInfo:
    """Hardware DMI information (Laptop vendor, product name, chassis type)."""
    vendor: str
    product: str
    chassis: str


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
class NetworkInfo:
    bytes_sent_per_sec: float = 0.0
    bytes_recv_per_sec: float = 0.0
    interface: str = ""
    ssid: Optional[str] = None
    band: Optional[str] = None          # "2.4 GHz" | "5 GHz" | "6 GHz"
    signal_percent: Optional[int] = None
    is_connected: bool = False
    total_sent_bytes: int = 0
    total_recv_bytes: int = 0


@dataclass
class PowerAnalytics:
    watts: Optional[float] = None
    is_charging: bool = False
    power_source: str = "AC"            # "AC" | "Battery"
    energy_now_wh: Optional[float] = None
    energy_full_wh: Optional[float] = None
    energy_design_wh: Optional[float] = None
    health_percent: Optional[float] = None
    wear_percent: Optional[float] = None
    cycle_count: Optional[int] = None
    seconds_left: Optional[int] = None


@dataclass
class QuickControlsState:
    brightness_percent: Optional[int] = None
    brightness_supported: bool = False
    turbo_enabled: Optional[bool] = None
    turbo_supported: bool = False
    volume_percent: Optional[int] = None
    is_muted: bool = False
    audio_supported: bool = False


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
    dmi: Optional[DmiInfo] = None
    network: Optional[NetworkInfo] = None
    power: Optional[PowerAnalytics] = None
    quick_controls: Optional[QuickControlsState] = None

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
# Hardware DMI Detection
# ---------------------------------------------------------------------------

_cached_dmi: Optional[DmiInfo] = None

def read_dmi() -> DmiInfo:
    global _cached_dmi
    if _cached_dmi is not None:
        return _cached_dmi
    dmi_path = Path("/sys/class/dmi/id")
    vendor = _read_str(dmi_path / "sys_vendor") or "Generic"
    product = _read_str(dmi_path / "product_name") or "Linux Computer"
    chassis_code = _read_str(dmi_path / "chassis_type") or "9"
    # Portable / Laptop chassis codes
    if chassis_code in ("8", "9", "10", "11", "14", "30", "31", "32"):
        chassis = "Laptop"
    elif chassis_code in ("3", "4", "5", "6", "7"):
        chassis = "Desktop"
    else:
        chassis = "PC"
    _cached_dmi = DmiInfo(vendor=vendor, product=product, chassis=chassis)
    return _cached_dmi


# ---------------------------------------------------------------------------
# Dynamic SMC and Fan Path Detection
# ---------------------------------------------------------------------------

def find_smc_path() -> Optional[Path]:
    """Find the Apple SMC sysfs path across different kernel builds."""
    candidates = [
        Path("/sys/devices/platform/applesmc.768"),
        Path("/sys/devices/platform/applesmc"),
    ]
    for c in candidates:
        if c.exists() and (c / "fan1_input").exists():
            return c
    try:
        for hw in Path("/sys/class/hwmon").glob("hwmon*"):
            if _read_str(hw / "name") == "applesmc":
                return hw
    except Exception:
        pass
    for c in candidates:
        if c.exists():
            return c
    return None


# ---------------------------------------------------------------------------
# Fans
# ---------------------------------------------------------------------------

def read_fans() -> list[FanInfo]:
    """Read fans from Apple SMC, Lenovo ThinkPad, ASUS, or generic Linux hwmon drivers."""
    fans: list[FanInfo] = []

    # 1. Lenovo ThinkPad ACPI interface
    tp_fan = Path("/proc/acpi/ibm/fan")
    if tp_fan.exists():
        try:
            lines = tp_fan.read_text().splitlines()
            speed = 0
            manual = False
            for line in lines:
                if line.startswith("speed:"):
                    speed = int(line.split(":")[1].strip())
                elif line.startswith("level:"):
                    lvl = line.split(":")[1].strip().lower()
                    manual = (lvl != "auto")
            fans.append(FanInfo(
                index=1,
                label="ThinkPad Fan",
                rpm=speed,
                min_rpm=0,
                max_rpm=5500,
                manual=manual,
            ))
            return fans
        except Exception:
            pass

    # 2. Apple SMC
    smc = find_smc_path()
    if smc is not None and list(smc.glob("fan*_input")):
        for input_file in sorted(smc.glob("fan*_input")):
            name = input_file.name
            try:
                idx = int(name.replace("fan", "").replace("_input", ""))
            except ValueError:
                continue
            rpm = _read_int(input_file) or 0
            label = _read_str(smc / f"fan{idx}_label") or f"Fan {idx}"
            mn = _read_int(smc / f"fan{idx}_min") or 0
            mx = _read_int(smc / f"fan{idx}_max") or 6500
            manual = bool(_read_int(smc / f"fan{idx}_manual") or 0)
            fans.append(FanInfo(index=idx, label=label, rpm=rpm, min_rpm=mn, max_rpm=mx, manual=manual))
        if fans:
            return fans

    # 2b. Apple SMC via macsmc (/dev/smc ioctl on Linux >= 6.13 / CachyOS / Asahi)
    try:
        from core.macsmc import has_macsmc, query_fans
        if has_macsmc():
            smc_fans = query_fans()
            if smc_fans:
                for f in smc_fans:
                    fans.append(FanInfo(
                        index=f.index,
                        label=f.label,
                        rpm=f.rpm,
                        min_rpm=f.min_rpm,
                        max_rpm=f.max_rpm,
                        manual=f.manual,
                    ))
                return fans
    except Exception:
        pass

    # 3. Generic Linux hwmon (e.g. Dell, ASUS, Acer, HP, Framework, Tuxedo, Clevo)
    try:
        fan_count = 0
        for hw in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
            fan_inputs = sorted(hw.glob("fan*_input"))
            if not fan_inputs:
                continue
            hw_name = _read_str(hw / "name") or "System"
            for input_file in fan_inputs:
                name = input_file.name
                try:
                    idx = int(name.replace("fan", "").replace("_input", ""))
                except ValueError:
                    continue
                fan_count += 1
                rpm = _read_int(input_file) or 0
                raw_label = _read_str(hw / f"fan{idx}_label")
                if raw_label:
                    label = raw_label
                elif fan_count == 1:
                    label = "CPU Fan"
                elif fan_count == 2:
                    label = "GPU Fan"
                else:
                    label = f"{hw_name} Fan {idx}"

                mn = _read_int(hw / f"fan{idx}_min") or 0
                mx = _read_int(hw / f"fan{idx}_max") or max(6000, rpm)
                manual = False
                pwm_en = hw / f"pwm{idx}_enable"
                if pwm_en.exists():
                    v = _read_int(pwm_en)
                    manual = (v == 1)
                fans.append(FanInfo(index=idx, label=label, rpm=rpm, min_rpm=mn, max_rpm=mx, manual=manual))
    except Exception:
        pass

    return fans


# ---------------------------------------------------------------------------
# Universal CPU temps (Intel coretemp, AMD k10temp/zenpower, ARM SoC, ACPI)
# ---------------------------------------------------------------------------

def _find_cpu_hwmon_devices() -> list[Path]:
    """Find CPU temperature hwmon devices across all architectures."""
    devices: list[Path] = []
    known = {"coretemp", "k10temp", "zenpower", "cpu_thermal", "soc_thermal", "acpitz", "macsmc_hwmon"}
    for hw in Path("/sys/class/hwmon").glob("hwmon*"):
        name = (_read_str(hw / "name") or "").lower()
        if name in known or "cpu" in name or "k10" in name or "thermal" in name:
            devices.append(hw)
    if not devices:
        for hw in Path("/sys/class/hwmon").glob("hwmon*"):
            for lbl in hw.glob("temp*_label"):
                txt = (_read_str(lbl) or "").lower()
                if any(k in txt for k in ("core", "package", "tctl", "tdie", "cpu")):
                    devices.append(hw)
                    break
    return devices


def read_cpu_temps() -> tuple[Optional[float], Optional[float], list[float]]:
    """Returns (max_core_temp, pkg_temp, [core_temps]). Universal across Intel, AMD, ARM."""
    devices = _find_cpu_hwmon_devices()
    if not devices:
        return None, None, []
    pkg_temp: Optional[float] = None
    core_temps: list[float] = []
    for hw in devices:
        for temp_input in sorted(hw.glob("temp*_input")):
            idx = temp_input.name.replace("temp", "").replace("_input", "")
            label = _read_str(hw / f"temp{idx}_label") or ""
            val = _read_float_milli(temp_input)
            if val is None or not (0 < val < 135):
                continue
            lbl_low = label.lower()
            if any(k in lbl_low for k in ("package", "tdie", "tctl")):
                if pkg_temp is None or val > pkg_temp:
                    pkg_temp = val
            elif any(k in lbl_low for k in ("core", "tccd")):
                core_temps.append(val)
            elif not label:
                core_temps.append(val)
    if pkg_temp is None and core_temps:
        pkg_temp = max(core_temps)
    max_core = max(core_temps) if core_temps else pkg_temp
    return max_core, pkg_temp, core_temps


def read_smc_extra_temps() -> dict[str, float]:
    """All hardware & SMC temps, keyed by friendly name when known and also by raw label.
    Supports legacy applesmc, modern macsmc_hwmon, and generic hwmon nodes."""
    import re
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
    search_paths: set[Path] = set()

    smc = find_smc_path()
    if smc is not None:
        search_paths.add(smc)
        smc_hwmon = smc / "hwmon"
        if smc_hwmon.exists():
            for sub in smc_hwmon.glob("hwmon*"):
                search_paths.add(sub)

    # Always scan all /sys/class/hwmon directories
    try:
        for hw in Path("/sys/class/hwmon").glob("hwmon*"):
            search_paths.add(hw)
    except Exception:
        pass

    for hw in search_paths:
        for temp_input in hw.glob("temp*_input"):
            idx = temp_input.name.replace("temp", "").replace("_input", "")
            label = _read_str(hw / f"temp{idx}_label") or ""
            val = _read_float_milli(temp_input)
            if val is None or not (-30 < val < 135):
                continue
            if label:
                out[label] = val
                # Extract 4-char SMC key from parentheses e.g. TC1C in "CPU Core 1 (TC1C)"
                m = re.search(r"\(([A-Za-z0-9_]{4})\)", label)
                if m:
                    key = m.group(1)
                    out[key] = val
                    if key in label_map:
                        out.setdefault(label_map[key], val)
                friendly = label_map.get(label)
                if friendly:
                    out.setdefault(friendly, val)
                # Friendly fallback heuristics
                low = label.lower()
                if "gpu" in low or "gfx" in low:
                    out.setdefault("GPU", val)
                elif "wireless" in low or "wifi" in low:
                    out.setdefault("WiFi", val)
                elif "heatpipe" in low:
                    out.setdefault("Heatpipe", val)
                elif "pch" in low:
                    out.setdefault("PCH", val)
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
# Universal GPU (Intel, AMD Radeon, NVIDIA)
# ---------------------------------------------------------------------------

_last_gpu_busy_ns: Optional[int] = None
_last_gpu_busy_time: Optional[float] = None
_cached_intel_card: Optional[Path] = None


def _find_intel_card() -> Optional[Path]:
    """Locate the Intel iGPU sysfs directory. Cards may be card0, card1, etc."""
    global _cached_intel_card
    if _cached_intel_card is not None and _cached_intel_card.exists():
        return _cached_intel_card
    candidates: list[Path] = []
    for card_path in sorted(DRM_PATH.glob("card*")):
        if not card_path.is_dir() or "-" in card_path.name:
            continue
        vendor_file = card_path / "device" / "vendor"
        try:
            if vendor_file.exists() and vendor_file.read_text().strip() == "0x8086":
                candidates.append(card_path)
        except Exception:
            continue
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

    # 1. Intel GPU
    card = _find_intel_card()
    if card is not None:
        cur = _read_int(card / "gt_cur_freq_mhz")
        mx = _read_int(card / "gt_max_freq_mhz")
        busy_pct: Optional[float] = None
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
                        busy_pct = min(100.0, max(0.0, db / dt_ns * 100.0 / max(1, len(busy_files))))
                _last_gpu_busy_ns = total_ns
                _last_gpu_busy_time = now
        return GpuInfo(cur_freq_mhz=cur, max_freq_mhz=mx, busy_percent=busy_pct)

    # 2. AMD Radeon (amdgpu driver)
    try:
        for card_path in sorted(DRM_PATH.glob("card*")):
            dev = card_path / "device"
            busy_file = dev / "gpu_busy_percent"
            if busy_file.exists():
                busy = _read_int(busy_file)
                cur_f = None
                for hw in (dev / "hwmon").glob("hwmon*") if (dev / "hwmon").exists() else []:
                    f = _read_int(hw / "freq1_input")
                    if f: cur_f = int(f / 1_000_000)
                return GpuInfo(cur_freq_mhz=cur_f, max_freq_mhz=None, busy_percent=float(busy) if busy is not None else None)
    except Exception:
        pass

    # 3. NVIDIA GPU (nvidia-smi)
    if shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,clocks.current.graphics,clocks.max.graphics",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=1,
            )
            if r.returncode == 0 and r.stdout.strip():
                parts = [p.strip() for p in r.stdout.strip().split(",")]
                util = float(parts[0]) if len(parts) > 0 and parts[0].replace(".", "", 1).isdigit() else None
                cur_c = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                max_c = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
                return GpuInfo(cur_freq_mhz=cur_c, max_freq_mhz=max_c, busy_percent=util)
        except Exception:
            pass

    return GpuInfo(cur_freq_mhz=None, max_freq_mhz=None, busy_percent=None)


# ---------------------------------------------------------------------------
# Universal Battery (BAT0, BAT1, BATT, any power supply)
# ---------------------------------------------------------------------------

def find_battery_path() -> Optional[Path]:
    """Dynamically locate battery across all laptop brands."""
    base = Path("/sys/class/power_supply")
    for p in sorted(base.glob("BAT*")):
        if (p / "voltage_now").exists() or (p / "capacity").exists() or (p / "energy_now").exists() or (p / "charge_now").exists():
            return p
    for p in base.glob("*"):
        try:
            if _read_str(p / "type") == "Battery":
                return p
        except Exception:
            pass
    return None


def read_battery() -> Optional[BatteryInfo]:
    bat_path = find_battery_path()
    try:
        bat = psutil.sensors_battery()
    except Exception:
        bat = None

    if bat is None and bat_path is None:
        return None

    try:
        pct = bat.percent if bat else None
        plugged = bat.power_plugged if bat else False
        seconds = int(bat.secsleft) if (bat and bat.secsleft is not None and bat.secsleft >= 0) else None

        voltage = None
        current = None
        temp_c = None
        cycle = None
        energy_full_wh = None
        energy_full_design_wh = None
        health = None

        if bat_path is not None:
            if pct is None:
                cap = _read_int(bat_path / "capacity")
                if cap is not None: pct = float(cap)

            # Voltage
            v = _read_float_milli(bat_path / "voltage_now")
            if v is not None: voltage = v / 1000.0

            # Current or Power
            c = _read_float_milli(bat_path / "current_now")
            if c is not None: current = c / 1000.0

            # Battery temp
            psup_temp = _read_int(bat_path / "temp")
            if psup_temp is not None:
                if 100 < psup_temp < 1000:
                    temp_c = psup_temp / 10.0
                elif 10000 < psup_temp < 100000:
                    temp_c = psup_temp / 1000.0

            # Health & cycles
            cycle = _read_int(bat_path / "cycle_count")
            ef = _read_int(bat_path / "energy_full") or _read_int(bat_path / "charge_full")
            efd = _read_int(bat_path / "energy_full_design") or _read_int(bat_path / "charge_full_design")
            if ef: energy_full_wh = ef / 1_000_000.0
            if efd: energy_full_design_wh = efd / 1_000_000.0
            if ef and efd and efd > 0:
                health = min(100.0, ef / efd * 100.0)

        if temp_c is None:
            extras = read_smc_extra_temps()
            temp_c = _get_temp(extras, "Battery", "TB0T")

        if pct is None:
            return None

        return BatteryInfo(
            percent=pct,
            plugged=plugged,
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
        r = subprocess.run(
            ["findmnt", "-no", "SOURCE", "/"],
            capture_output=True, text=True, timeout=2,
        )
        src = r.stdout.strip()
        if not src:
            return None
        # Clean Btrfs/ZFS subvolume tags like /dev/sda2[/@] -> /dev/sda2
        if "[" in src:
            src = src.split("[")[0]
        # Strip /dev/
        name = src.replace("/dev/", "")
        # Handle nvme, mmcblk, standard sdX/vdX/hdX
        import re as _re
        m = _re.match(r"^(nvme\d+n\d+|mmcblk\d+|[a-z]+)", name)
        if m:
            return m.group(1)
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
            elif "drivetemp" in name.lower():
                t = _read_float_milli(hw / "temp1_input")
                if t is not None:
                    temp_c = t
                    break

    # Fallback: Apple SMC drive sensors (TH0A, TH0B, TH0C, etc.)
    if temp_c is None:
        try:
            extra = read_smc_extra_temps()
            for key in ("TH0A", "TH0a", "TH0B", "TH0b", "TH0C", "TH0c", "Drive 0"):
                for ek, ev in extra.items():
                    if key in ek and ev > 0:
                        temp_c = float(ev)
                        break
                if temp_c is not None:
                    break
        except Exception:
            pass
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
# Network, Power Analytics, and Quick Controls
# ---------------------------------------------------------------------------

_last_net_bytes: Optional[tuple[float, int, int]] = None  # (time, recv, sent)
_cached_wifi: tuple[float, Optional[str], Optional[str], Optional[int]] = (-10.0, None, None, None)


def _read_wifi_details() -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Query Wi-Fi SSID, frequency band ('2.4 GHz' / '5 GHz' / '6 GHz'), and signal %."""
    ssid: Optional[str] = None
    band: Optional[str] = None
    signal: Optional[int] = None

    # Check via nmcli if present
    if shutil.which("nmcli"):
        try:
            r = subprocess.run(
                ["nmcli", "-t", "-f", "active,ssid,signal,freq", "dev", "wifi"],
                capture_output=True, text=True, timeout=1.5
            )
            for line in r.stdout.splitlines():
                parts = line.strip().split(":")
                if len(parts) >= 4 and parts[0].lower() in ("yes", "sì", "si", "true", "ja", "oui", "1"):
                    ssid = parts[1].strip() or None
                    try:
                        signal = int(parts[2].strip())
                    except Exception:
                        pass
                    try:
                        freq_val = int(parts[3].replace("MHz", "").strip())
                        if freq_val >= 5900:
                            band = "6 GHz"
                        elif freq_val >= 4900:
                            band = "5 GHz"
                        else:
                            band = "2.4 GHz"
                    except Exception:
                        pass
                    if ssid:
                        return ssid, band, signal
        except Exception:
            pass

    # Fallback to iw
    if shutil.which("iw"):
        try:
            r = subprocess.run(["iw", "dev"], capture_output=True, text=True, timeout=1.0)
            cur_iface = None
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.startswith("Interface "):
                    cur_iface = line.split()[1]
                elif line.startswith("ssid ") and cur_iface:
                    ssid = line[5:].strip()
            if cur_iface:
                r_link = subprocess.run(["iw", "dev", cur_iface, "link"], capture_output=True, text=True, timeout=1.0)
                for l in r_link.stdout.splitlines():
                    l = l.strip()
                    if l.startswith("SSID: ") and not ssid:
                        ssid = l[6:].strip()
                    elif l.startswith("freq: "):
                        try:
                            fval = float(l[6:].strip())
                            if fval >= 5900:
                                band = "6 GHz"
                            elif fval >= 4900:
                                band = "5 GHz"
                            else:
                                band = "2.4 GHz"
                        except Exception:
                            pass
                    elif l.startswith("signal: "):
                        try:
                            dbm = float(l.split()[1])
                            signal = int(max(0, min(100, 2 * (dbm + 100))))
                        except Exception:
                            pass
        except Exception:
            pass

    return ssid, band, signal


def read_network() -> NetworkInfo:
    """Read network bandwidth throughput and connection info."""
    global _last_net_bytes, _cached_wifi
    now = time.time()
    try:
        net = psutil.net_io_counters()
        recv_total = net.bytes_recv
        sent_total = net.bytes_sent
    except Exception:
        return NetworkInfo()

    down_rate = 0.0
    up_rate = 0.0
    if _last_net_bytes is not None:
        dt = max(0.1, now - _last_net_bytes[0])
        down_rate = max(0.0, (recv_total - _last_net_bytes[1]) / dt)
        up_rate = max(0.0, (sent_total - _last_net_bytes[2]) / dt)
    _last_net_bytes = (now, recv_total, sent_total)

    ssid, band, signal = _cached_wifi[1], _cached_wifi[2], _cached_wifi[3]
    if (now - _cached_wifi[0]) > 4.0:
        ssid, band, signal = _read_wifi_details()
        _cached_wifi = (now, ssid, band, signal)

    iface = ""
    try:
        stats = psutil.net_if_stats()
        for name, s in stats.items():
            if s.isup and not name.startswith(("lo", "docker", "veth", "virbr")):
                iface = name
                break
    except Exception:
        pass

    return NetworkInfo(
        bytes_sent_per_sec=up_rate,
        bytes_recv_per_sec=down_rate,
        interface=iface,
        ssid=ssid,
        band=band,
        signal_percent=signal,
        is_connected=bool(iface),
        total_sent_bytes=sent_total,
        total_recv_bytes=recv_total,
    )


def read_power_analytics(battery: Optional[BatteryInfo],
                         cpu_freq_mhz: Optional[float] = None,
                         cpu_freq_max_mhz: Optional[float] = None,
                         cpu_percent: float = 0.0) -> PowerAnalytics:
    """Read real-time power draw (Watts), wear level, and charging state."""
    watts: Optional[float] = None
    is_charging = False
    source = "AC"
    energy_now_wh = None
    energy_full_wh = None
    energy_design_wh = None
    health_percent = None
    wear_percent = None
    cycle_count = None
    seconds_left = None

    if battery is not None:
        is_charging = battery.plugged and (battery.seconds_left is None and battery.percent < 99.0)
        source = "AC" if battery.plugged else "Battery"
        energy_full_wh = battery.energy_full_wh
        energy_design_wh = battery.energy_full_design_wh
        health_percent = battery.health_percent
        if health_percent is not None:
            wear_percent = max(0.0, min(100.0, 100.0 - health_percent))
        cycle_count = battery.cycle_count
        seconds_left = battery.seconds_left

        if battery.voltage_v is not None and battery.current_a is not None and battery.current_a > 0:
            watts = round(battery.voltage_v * battery.current_a, 1)

    if watts is None:
        for ps in Path("/sys/class/power_supply").glob("BAT*"):
            p_now = ps / "power_now"
            if p_now.exists():
                val = _read_int(p_now)
                if val and val > 0:
                    watts = round(val / 1e6, 1)
                    break

    if watts is None:
        freq_ratio = (cpu_freq_mhz / (cpu_freq_max_mhz or 2500.0)) if cpu_freq_mhz else 0.5
        load_ratio = cpu_percent / 100.0
        base_w = 4.0
        dyn_w = 11.0 * freq_ratio * (0.3 + 0.7 * load_ratio)
        watts = round(base_w + dyn_w, 1)

    return PowerAnalytics(
        watts=watts,
        is_charging=is_charging,
        power_source=source,
        energy_now_wh=energy_now_wh,
        energy_full_wh=energy_full_wh,
        energy_design_wh=energy_design_wh,
        health_percent=health_percent,
        wear_percent=wear_percent,
        cycle_count=cycle_count,
        seconds_left=seconds_left,
    )


def read_quick_controls() -> QuickControlsState:
    """Read screen brightness, turbo boost state, and audio volume."""
    b_pct: Optional[int] = None
    b_supported = False
    for b in Path("/sys/class/backlight").glob("*"):
        b_cur = b / "brightness"
        b_max = b / "max_brightness"
        if b_cur.exists() and b_max.exists():
            cur_v = _read_int(b_cur)
            max_v = _read_int(b_max)
            if cur_v is not None and max_v is not None and max_v > 0:
                b_pct = int(round(cur_v / max_v * 100.0))
                b_supported = True
                break

    turbo_enabled: Optional[bool] = None
    turbo_supported = False
    pstate_no_turbo = Path("/sys/devices/system/cpu/intel_pstate/no_turbo")
    cpufreq_boost = Path("/sys/devices/system/cpu/cpufreq/boost")
    if pstate_no_turbo.exists():
        turbo_supported = True
        v = _read_str(pstate_no_turbo)
        turbo_enabled = (v == "0")
    elif cpufreq_boost.exists():
        turbo_supported = True
        v = _read_str(cpufreq_boost)
        turbo_enabled = (v == "1")

    vol_pct: Optional[int] = None
    is_muted = False
    audio_supported = False
    if shutil.which("wpctl"):
        try:
            r = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                               capture_output=True, text=True, timeout=0.5)
            if r.returncode == 0:
                line = r.stdout.strip()
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        vol_f = float(parts[1])
                        vol_pct = int(round(vol_f * 100.0))
                        is_muted = "[MUTED]" in line
                        audio_supported = True
                    except Exception:
                        pass
        except Exception:
            pass

    return QuickControlsState(
        brightness_percent=b_pct,
        brightness_supported=b_supported,
        turbo_enabled=turbo_enabled,
        turbo_supported=turbo_supported,
        volume_percent=vol_pct,
        is_muted=is_muted,
        audio_supported=audio_supported,
    )


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
    bat = read_battery()
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
        battery=bat,
        memory=read_memory(),
        top_processes=read_top_processes(top_processes_limit) if include_top_processes else [],
        extra_temps=read_smc_extra_temps(),
        throttle=read_throttle(),
        disk=read_disk() if include_disk else None,
        dmi=read_dmi(),
        network=read_network(),
        power=read_power_analytics(bat, f_cur, f_max, load_total),
        quick_controls=read_quick_controls(),
    )


def format_seconds(s: Optional[int]) -> str:
    if s is None:
        return "—"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h{m:02d}m" if h else f"{m}m"
