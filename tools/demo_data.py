# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic, reproducible telemetry for screenshots and render regression tests."""
from core import sensors as s


def demo_snapshot():
    gib = 1024**3
    return s.Snapshot(
        timestamp=0, cpu_temp_c=48.5, cpu_pkg_temp_c=48.5,
        cpu_core_temps=[46.0, 48.5, 44.0, 45.5],
        cpu_percent_total=18, cpu_percent_per_core=[12, 24, 16, 20],
        cpu_freq_mhz=1800, cpu_freq_max_mhz=3200,
        fans=[s.FanInfo(1, 'Fan 1', 1800, 1200, 6500)],
        gpu=s.GpuInfo(450, 1100, 8),
        battery=s.BatteryInfo(82, True, None, 30, 12.2, .6, 120, 45, 50, 90),
        memory=s.MemoryInfo(16*gib, 5*gib, 11*gib, 31.25, 4*gib, gib//4, 6.25),
        top_processes=[s.TopProcess(1234, 'Example app', 8, 2, gib//3)],
        extra_temps={'GPU Core': 44.0, 'SSD': 34.0},
        throttle=s.ThrottleInfo(0, 0, False, None),
        disk=s.DiskInfo('nvme0n1', 'Example NVMe SSD', 34.0, 1200, 250, 'OK'),
        dmi=s.DmiInfo('Example', 'Linux Laptop', 'Laptop'),
        network=s.NetworkInfo(24*1024, 512*1024, 'wlan0', 'Example Wi-Fi', '5 GHz', 85, True),
        power=s.PowerAnalytics(watts=12.5, power_source='AC', health_percent=90, wear_percent=10, cycle_count=120),
        quick_controls=s.QuickControlsState(70, True, True, True, 45, False, True),
    )
