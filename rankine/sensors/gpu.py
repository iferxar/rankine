"""GPU metrics. amdgpu is read from sysfs, NVIDIA through nvidia-smi, Intel partially."""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess

from .hwmon import Chip, by_name, read_int, read_text

GIB = 1024 ** 3


# PCI IDs that lspci names as a whole family; the revision tells the models apart.
_BY_REVISION = {
    ("0x1002", "0x73bf"): {"0xc0": "AMD Radeon RX 6900 XT", "0xc1": "AMD Radeon RX 6800 XT",
                           "0xc3": "AMD Radeon RX 6800"},
}


def pci_name(device_path: str | None) -> str | None:
    """Human name of a PCI device via lspci, e.g. 'AMD Radeon RX 6800/6800 XT / 6900 XT', narrowed
    to the exact model by revision where the family shares one ID."""
    if not device_path:
        return None
    ids = tuple(read_text(f"{device_path}/{f}") for f in ("vendor", "device"))
    exact = _BY_REVISION.get(ids, {}).get(read_text(f"{device_path}/revision"))
    if exact:
        return exact
    if not shutil.which("lspci"):
        return None
    try:
        out = subprocess.run(["lspci", "-s", os.path.basename(device_path)],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if ": " not in out:
        return None
    desc = re.sub(r"\s*\(rev [^)]*\)\s*$", "", out.split(": ", 1)[1].strip())
    vendor = next((v for v in ("AMD", "NVIDIA", "Intel") if v.lower() in desc.lower()), "")
    brackets = re.findall(r"\[([^\]]+)\]", desc)
    model = brackets[-1] if brackets and brackets[-1] not in ("AMD/ATI",) else desc
    return f"{vendor} {model}".strip() if vendor and not model.startswith(vendor) else model


def _value(ch):
    return ch.value() if ch else None


class AmdGpu:
    def __init__(self, chip: Chip):
        self.chip = chip
        self.dev = chip.device
        self.name = read_text(f"{self.dev}/product_name") or pci_name(self.dev) or "AMD GPU"
        self.temp = chip.find("temp", "edge") or chip.find("temp")
        self.hotspot = chip.find("temp", "junction")
        self.mem_temp = chip.find("temp", "mem")
        self.clock = chip.find("freq", "sclk")
        self.power = chip.find("power", "PPT") or chip.find("power")
        self.volt = chip.find("in", "vddgfx") or chip.find("in")
        self.fan = chip.find("fan")
        self.fan_max = self.fan.attr("max") if self.fan else None

    @property
    def vram_total(self) -> int:
        return read_int(f"{self.dev}/mem_info_vram_total") or 0

    def read(self) -> dict:
        power, volt = _value(self.power), _value(self.volt)
        used = read_int(f"{self.dev}/mem_info_vram_used")
        total = self.vram_total
        return {
            "name": self.name,
            "temp": _value(self.temp),
            "hotspot": _value(self.hotspot),
            "mem_temp": _value(self.mem_temp),
            "load": read_int(f"{self.dev}/gpu_busy_percent"),
            "mhz": _value(self.clock),
            "power": power,
            "voltage": volt,
            "current": power / volt if power is not None and volt and volt > 0.3 else None,
            "vram_used": used / GIB if used is not None else None,
            "vram_total": total / GIB if total else None,
            "fan_rpm": _value(self.fan),
            "fan_max": self.fan_max,
            "fan_percent": None,
        }


class NvidiaGpu:
    _FIELDS = ["name", "temperature.gpu", "utilization.gpu", "clocks.gr", "power.draw",
               "memory.used", "memory.total", "fan.speed"]

    def __init__(self):
        self.name = (self._query() or {}).get("name") or "NVIDIA GPU"

    def _query(self) -> dict | None:
        try:
            out = subprocess.run(
                ["nvidia-smi", f"--query-gpu={','.join(self._FIELDS)}",
                 "--format=csv,noheader,nounits", "-i", "0"],
                capture_output=True, text=True, timeout=2).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        parts = [p.strip() for p in out.strip().split(",")]
        if len(parts) != len(self._FIELDS):
            return None
        return dict(zip(self._FIELDS, parts))

    @staticmethod
    def _num(text):
        try:
            return float(text)
        except (TypeError, ValueError):
            return None

    def read(self) -> dict:
        q = self._query() or {}
        n = self._num
        used, total = n(q.get("memory.used")), n(q.get("memory.total"))
        return {
            "name": self.name,
            "temp": n(q.get("temperature.gpu")),
            "hotspot": None,
            "mem_temp": None,
            "load": n(q.get("utilization.gpu")),
            "mhz": n(q.get("clocks.gr")),
            "power": n(q.get("power.draw")),
            "voltage": None,
            "current": None,
            "vram_used": used / 1024 if used is not None else None,
            "vram_total": total / 1024 if total is not None else None,
            "fan_rpm": None,
            "fan_max": None,
            "fan_percent": n(q.get("fan.speed")),
        }


class IntelGpu:
    def __init__(self, card: str, chip: Chip | None):
        self.card = card
        self.chip = chip
        self.name = pci_name(os.path.realpath(f"{card}/device")) or "Intel GPU"

    def read(self) -> dict:
        mhz = read_int(f"{self.card}/gt_act_freq_mhz")
        if mhz is None:
            mhz = read_int(f"{self.card}/device/tile0/gt0/freq0/act_freq")  # xe driver
        return {
            "name": self.name, "temp": _value(self.chip.find("temp")) if self.chip else None,
            "hotspot": None, "mem_temp": None, "load": None, "mhz": mhz,
            "power": None, "voltage": _value(self.chip.find("in")) if self.chip else None,
            "current": None, "vram_used": None, "vram_total": None,
            "fan_rpm": None, "fan_max": None, "fan_percent": None,
        }


def detect_gpu(chips: list[Chip]):
    amd = [AmdGpu(c) for c in by_name(chips, "amdgpu") if c.device]
    if amd:
        return max(amd, key=lambda g: g.vram_total)  # discrete over integrated
    if shutil.which("nvidia-smi"):
        gpu = NvidiaGpu()
        if gpu._query():
            return gpu
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]")):
        if read_text(f"{card}/device/vendor") == "0x8086":
            dev = os.path.realpath(f"{card}/device")
            chip = next((c for c in by_name(chips, "i915", "xe") if c.device == dev), None)
            return IntelGpu(card, chip)
    return None
