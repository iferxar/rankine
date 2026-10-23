"""Combines every reader into one snapshot per tick, with min/avg/max stats and history."""
from __future__ import annotations

import math
import random
import time
from collections import deque

from .cpu import CpuReader
from .gpu import detect_gpu
from .hwmon import discover
from .system import DriveReader, FanReader, MemoryReader, save_dimm_cache

HISTORY_LEN = 120
HISTORY_KEYS = ("cpu.temp", "cpu.load", "gpu.temp", "gpu.load", "mem.percent",
                "gpu.power", "gpu.mhz", "gpu.hotspot", "gpu.fan_rpm")


class Stats:
    def __init__(self):
        self.reset()

    def reset(self):
        self._data: dict[str, list[float]] = {}  # key -> [min, max, sum, count]

    def update(self, key: str, value):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or math.isnan(value):
            return
        s = self._data.get(key)
        if s is None:
            self._data[key] = [value, value, value, 1]
        else:
            s[0] = min(s[0], value)
            s[1] = max(s[1], value)
            s[2] += value
            s[3] += 1

    def snapshot(self) -> dict:
        return {k: {"min": s[0], "max": s[1], "avg": s[2] / s[3]} for k, s in self._data.items()}


def status_for(*temps) -> str:
    hottest = max((t for t in temps if t is not None), default=None)
    if hottest is None:
        return "N/A"
    return "COOL" if hottest < 65 else "WARM" if hottest < 85 else "HOT"


class BaseMonitor:
    def __init__(self):
        self.stats = Stats()
        self.history = {k: deque(maxlen=HISTORY_LEN) for k in HISTORY_KEYS}

    def reset_stats(self):
        self.stats.reset()

    def save_dimm_info(self, dmidecode_output: str) -> bool:
        """Stores configured DIMM speed/voltage from a privileged dmidecode run."""
        return False

    def read(self) -> dict:
        raise NotImplementedError

    def sample(self) -> dict:
        snap = self.read()
        for section in ("cpu", "gpu", "mem"):
            for key, value in (snap.get(section) or {}).items():
                self.stats.update(f"{section}.{key}", value)
        for fan in snap["fans"]:
            self.stats.update(f"fan.{fan['name']}", fan["rpm"])
        for key, buf in self.history.items():
            section, field = key.split(".")
            value = (snap.get(section) or {}).get(field)
            buf.append(value if value is not None else (buf[-1] if buf else 0))
        snap["stats"] = self.stats.snapshot()
        snap["history"] = {k: list(v) for k, v in self.history.items()}
        snap["status"] = status_for(snap["cpu"].get("temp"), (snap.get("gpu") or {}).get("temp"))
        return snap


class Monitor(BaseMonitor):
    def __init__(self):
        super().__init__()
        chips = discover()
        self.cpu = CpuReader(chips)
        self.gpu = detect_gpu(chips)
        self.mem = MemoryReader(chips)
        self.fans = FanReader(chips, exclude=getattr(self.gpu, "chip", None))
        self.drives = DriveReader(chips)

    def save_dimm_info(self, dmidecode_output: str) -> bool:
        if not save_dimm_cache(dmidecode_output, self.mem.modules):
            return False
        self.mem.reload_dimm_info()
        return True

    def read(self) -> dict:
        gpu = self.gpu.read() if self.gpu else None
        fans = self.fans.read()
        if gpu and (gpu["fan_rpm"] is not None or gpu["fan_percent"] is not None):
            if gpu["fan_rpm"] is not None:
                top = gpu["fan_max"] or 3000
                fans.append({"name": "GPU", "rpm": gpu["fan_rpm"],
                             "text": f"{gpu['fan_rpm']:.0f} RPM", "frac": min(1.0, gpu["fan_rpm"] / top)})
            else:
                fans.append({"name": "GPU", "rpm": None, "text": f"{gpu['fan_percent']:.0f} %",
                             "frac": gpu["fan_percent"] / 100})
        return {"cpu": self.cpu.read(), "gpu": gpu, "mem": self.mem.read(),
                "fans": fans, "drives": self.drives.read()}


class DemoMonitor(BaseMonitor):
    """Simulated telemetry, for screenshots and machines without sensors."""

    def __init__(self, threads: int = 16):
        super().__init__()
        self.threads = threads
        self.t0 = time.monotonic()

    def read(self) -> dict:
        t = time.monotonic() - self.t0
        wave = (math.sin(t / 9) + 1) / 2
        load = 8 + 60 * wave ** 3 + random.uniform(-3, 3)
        cores = [{"id": i, "load": max(0, min(100, load + random.uniform(-15, 25))),
                  "mhz": 3600 + 1200 * wave + random.uniform(-150, 150)} for i in range(self.threads)]
        cpu_power = 35 + 90 * wave ** 3
        gpu_load = max(0, 5 + 85 * ((math.sin(t / 13 + 1) + 1) / 2) ** 4 + random.uniform(-2, 2))
        gpu_power = 15 + 2.2 * gpu_load
        return {
            "cpu": {"name": "Demo CPU 16-Core", "temp": 42 + 35 * wave + random.uniform(-1, 1),
                    "temp_source": "demo", "load": load,
                    "mhz": sum(c["mhz"] for c in cores) / len(cores), "power": cpu_power,
                    "power_hint": None, "voltage": 1.1 + 0.25 * wave, "voltage_estimated": True,
                    "current": cpu_power / (1.1 + 0.25 * wave), "cores": cores},
            "gpu": {"name": "Demo GPU", "temp": 38 + 0.4 * gpu_load, "hotspot": 45 + 0.5 * gpu_load,
                    "mem_temp": 40 + 0.3 * gpu_load, "load": gpu_load, "mhz": 500 + 22 * gpu_load,
                    "power": gpu_power, "voltage": 0.75 + 0.004 * gpu_load,
                    "current": gpu_power / (0.75 + 0.004 * gpu_load),
                    "vram_used": 1.2 + 6 * gpu_load / 100, "vram_total": 16.0,
                    "fan_rpm": 0 if gpu_load < 30 else 900 + 12 * gpu_load, "fan_max": 3100,
                    "fan_percent": None},
            "mem": {"used": 9.6 + wave, "total": 31.3, "percent": 100 * (9.6 + wave) / 31.3,
                    "swap_used": 0.2, "swap_total": 16.0, "cached": 8.4, "clock": 3600,
                    "voltage": 1.35, "dimm_detected": True, "temp": None, "modules": "2 × 16 GB",
                    "mem_type": "DDR4", "part": "Demo DDR4-3600 kit", "rated_clock": 3600,
                    "rated_cl": 18, "rated_voltage": 1.35, "rated_profile": "XMP"},
            "fans": [{"name": f"Fan #{i}", "rpm": r, "text": f"{r:.0f} RPM", "frac": r / 2500}
                     for i, r in ((1, 900 + 600 * wave), (3, 1100 + 500 * wave), (4, 1200 + 400 * wave))],
            "drives": [{"name": "Demo NVMe SSD", "temp": 36 + 8 * wave, "max": 70}],
        }
