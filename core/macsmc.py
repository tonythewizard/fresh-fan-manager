# SPDX-License-Identifier: GPL-3.0-or-later
"""
macsmc — Native Linux interface for Apple SMC via /dev/smc ioctl.
Supports modern kernels (CachyOS, Asahi Linux, upstream Linux >= 6.13)
where legacy applesmc has been replaced by macsmc_core / macsmc_hwmon.
"""
from __future__ import annotations

import fcntl
import os
import struct
from pathlib import Path
from typing import Optional, NamedTuple

SMC_DEVICE = Path("/dev/smc")

# ioctl definitions matching <linux/mfd/macsmc.h>
APPLE_SMC_MAGIC = ord("S")  # 0x53
# _IOWR('S', 1, 48)
IOCTL_SMC_READ = 0xC0305301
# _IOW('S', 2, 48)
IOCTL_SMC_WRITE = 0x40305302
# _IOWR('S', 3, 8)
IOCTL_SMC_GET_KEY_INDEX = 0xC0085303
# _IOWR('S', 4, 12)
IOCTL_SMC_GET_KEY_INFO = 0xC00C5304


def has_macsmc() -> bool:
    """Return True if the macsmc kernel device /dev/smc exists."""
    return SMC_DEVICE.exists()


def is_macsmc_accessible() -> bool:
    """Return True if /dev/smc can be opened by the current process."""
    if not SMC_DEVICE.exists():
        return False
    try:
        fd = os.open(str(SMC_DEVICE), os.O_RDONLY)
        os.close(fd)
        return True
    except Exception:
        return False


def _smc_key(key_str: str) -> int:
    b = key_str.encode("ascii").ljust(4, b" ")
    return (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]


def smc_read(fd: int, key_str: str, size: int) -> Optional[bytes]:
    """Read `size` bytes from SMC key `key_str`."""
    try:
        k = _smc_key(key_str)
        payload = bytearray(struct.pack("<IIQ32s", k, 0, size, b"\x00" * 32))
        fcntl.ioctl(fd, IOCTL_SMC_READ, payload)
        return bytes(payload[16 : 16 + size])
    except Exception:
        return None


def smc_write(fd: int, key_str: str, data: bytes) -> bool:
    """Write `data` to SMC key `key_str`."""
    try:
        k = _smc_key(key_str)
        size = len(data)
        pad_data = data.ljust(32, b"\x00")
        payload = bytearray(struct.pack("<IIQ32s", k, 0, size, pad_data))
        fcntl.ioctl(fd, IOCTL_SMC_WRITE, payload)
        return True
    except Exception:
        return False


def smc_get_key_info(fd: int, key_str: str) -> Optional[tuple[str, int, int]]:
    """Return (type_code_str, size, flags) or None."""
    try:
        k = _smc_key(key_str)
        payload = bytearray(struct.pack("<IIBBxx", k, 0, 0, 0))
        fcntl.ioctl(fd, IOCTL_SMC_GET_KEY_INFO, payload)
        _, type_code, size, flags = struct.unpack("<IIBBxx", payload)
        type_bytes = struct.pack(">I", type_code)
        type_str = type_bytes.decode("ascii", errors="replace").strip("\x00")
        return (type_str, size, flags)
    except Exception:
        return None


def decode_rpm(buf: Optional[bytes], type_code: Optional[str] = None) -> Optional[float]:
    """Decode raw SMC bytes into RPM float value."""
    if not buf:
        return None
    try:
        if type_code == "flt" and len(buf) >= 4:
            return float(struct.unpack(">f", buf[:4])[0])
        if type_code == "ioft" and len(buf) >= 8:
            val = struct.unpack(">Q", buf[:8])[0]
            return float(val >> 16)
        if len(buf) >= 2:
            raw = (buf[0] << 8) | buf[1]
            # Standard Apple SMC fpe2 format: 14.2 fixed point
            return float(raw >> 2) + float(raw & 3) * 0.25
        if len(buf) == 1:
            return float(buf[0])
    except Exception:
        pass
    return None


def encode_rpm_fpe2(rpm: int) -> bytes:
    """Encode RPM integer into 2-byte fpe2 format."""
    val = max(0, min(8000, int(rpm))) << 2
    return bytes([(val >> 8) & 0xFF, val & 0xFF])


class MacSmcFan(NamedTuple):
    index: int
    label: str
    rpm: int
    min_rpm: int
    max_rpm: int
    target_rpm: int
    manual: bool


def query_fans() -> list[MacSmcFan]:
    """Query fans via /dev/smc. Returns list of MacSmcFan."""
    if not SMC_DEVICE.exists():
        return []

    try:
        fd = os.open(str(SMC_DEVICE), os.O_RDWR)
    except Exception:
        try:
            fd = os.open(str(SMC_DEVICE), os.O_RDONLY)
        except Exception:
            return []

    fans: list[MacSmcFan] = []
    try:
        # Determine fan count
        fnum_data = smc_read(fd, "FNum", 1)
        fnum = fnum_data[0] if fnum_data else 0
        if fnum == 0:
            # Fallback: check if F0Ac exists
            if smc_read(fd, "F0Ac", 2) is not None:
                fnum = 1
            else:
                return []

        # Read global manual flag FS! (2 bytes bitmask on Intel Macs)
        fs_buf = smc_read(fd, "FS! ", 2)
        global_manual_mask = 0
        if fs_buf and len(fs_buf) >= 2:
            global_manual_mask = (fs_buf[0] << 8) | fs_buf[1]

        for i in range(fnum):
            actual_key = f"F{i}Ac"
            min_key = f"F{i}Mn"
            max_key = f"F{i}Mx"
            target_key = f"F{i}Tg"
            mode_key = f"F{i}Md"
            id_key = f"F{i}ID"

            actual_info = smc_get_key_info(fd, actual_key)
            type_code = actual_info[0] if actual_info else "fpe2"
            rpm_val = decode_rpm(smc_read(fd, actual_key, 2), type_code) or 0.0

            min_val = decode_rpm(smc_read(fd, min_key, 2), type_code) or 1200.0
            max_val = decode_rpm(smc_read(fd, max_key, 2), type_code) or 6500.0
            target_val = decode_rpm(smc_read(fd, target_key, 2), type_code) or rpm_val

            # Determine manual mode
            is_manual = bool((global_manual_mask >> i) & 1)
            # Or per-fan mode key (T2 / Apple Silicon)
            md_buf = smc_read(fd, mode_key, 1)
            if md_buf:
                is_manual = is_manual or bool(md_buf[0] != 0)

            # Fan Label
            label = f"Fan {i + 1}"
            id_buf = smc_read(fd, id_key, 16)
            if id_buf:
                # First byte is often length or string starts directly
                cleaned = id_buf.decode("ascii", errors="ignore").strip("\x00 \t\r\n")
                if cleaned and len(cleaned) > 1:
                    label = cleaned

            fans.append(
                MacSmcFan(
                    index=i + 1,
                    label=label if fnum > 1 else "Mac Fan",
                    rpm=int(round(rpm_val)),
                    min_rpm=int(round(min_val)),
                    max_rpm=int(round(max_val)),
                    target_rpm=int(round(target_val)),
                    manual=is_manual,
                )
            )
    finally:
        os.close(fd)

    return fans


def set_fan_manual(fan_index: int, manual: bool) -> bool:
    """Set fan to manual or automatic mode via /dev/smc."""
    if not SMC_DEVICE.exists():
        return False
    try:
        fd = os.open(str(SMC_DEVICE), os.O_RDWR)
    except Exception:
        return False

    idx = max(0, fan_index - 1)
    try:
        # 1. Update FS! (Intel Mac global bitmask)
        fs_buf = smc_read(fd, "FS! ", 2)
        if fs_buf and len(fs_buf) >= 2:
            mask = (fs_buf[0] << 8) | fs_buf[1]
            if manual:
                mask |= 1 << idx
            else:
                mask &= ~(1 << idx)
            fs_write = bytes([(mask >> 8) & 0xFF, mask & 0xFF])
            smc_write(fd, "FS! ", fs_write)

        # 2. Update F{idx}Md (T2 / Apple Silicon per-fan key)
        mode_key = f"F{idx}Md"
        smc_write(fd, mode_key, bytes([1 if manual else 0]))
        return True
    finally:
        os.close(fd)


def set_fan_rpm(fan_index: int, rpm: int) -> bool:
    """Write target fan RPM to /dev/smc."""
    if not SMC_DEVICE.exists():
        return False
    try:
        fd = os.open(str(SMC_DEVICE), os.O_RDWR)
    except Exception:
        return False

    idx = max(0, fan_index - 1)
    try:
        target_key = f"F{idx}Tg"
        target_data = encode_rpm_fpe2(rpm)
        return smc_write(fd, target_key, target_data)
    finally:
        os.close(fd)
