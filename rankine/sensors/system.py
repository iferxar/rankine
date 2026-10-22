"""Memory, fans and drive temperatures."""
from __future__ import annotations

import os
import re
import subprocess

from .hwmon import Chip, by_name, read_text

GIB = 1024 ** 3
DMI_CACHE = os.path.expanduser("~/.cache/rankine/dmidecode-memory.txt")


def _meminfo() -> dict[str, int]:
    out = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, rest = line.split(":", 1)
            out[key] = int(rest.split()[0]) * 1024
    return out


def parse_dmidecode(text: str) -> dict:
    """Configured speed and voltage of the first populated DIMM in `dmidecode -t 17` output."""
    for block in text.split("\n\n"):
        if "Memory Device" not in block or re.search(r"^\s*Size: No Module", block, re.M):
            continue
        speed = re.search(r"Configured (?:Memory|Clock) Speed: (\d+) MT/s", block)
        volt = re.search(r"Configured Voltage: ([\d.]+) V", block)
        if speed or volt:
            return {"clock": int(speed.group(1)) if speed else None,
                    "voltage": float(volt.group(1)) if volt else None}
    return {}


def probe_dimms() -> dict:
    """dmidecode needs root; fall back to a dump the user saved once with sudo."""
    try:
        res = subprocess.run(["dmidecode", "-t", "17"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            info = parse_dmidecode(res.stdout)
            if info:
                return info
    except (OSError, subprocess.SubprocessError):
        pass
    text = read_text(DMI_CACHE)
    return parse_dmidecode(text) if text else {}


class MemoryReader:
    def __init__(self, chips: list[Chip]):
        self.temps = [c.find("temp") for c in by_name(chips, "spd5118", "jc42") if c.find("temp")]
        self.dimm = probe_dimms()

    def read(self) -> dict:
        m = _meminfo()
        total = m.get("MemTotal", 0)
        used = total - m.get("MemAvailable", m.get("MemFree", 0))
        swap_total = m.get("SwapTotal", 0)
        temps = [t for t in (ch.value() for ch in self.temps) if t is not None]
        return {
            "used": used / GIB,
            "total": total / GIB,
            "percent": 100 * used / total if total else None,
            "swap_used": (swap_total - m.get("SwapFree", 0)) / GIB,
            "swap_total": swap_total / GIB,
            "clock": self.dimm.get("clock"),
            "voltage": self.dimm.get("voltage"),
            "temp": max(temps) if temps else None,
            "dimm_hint": None if self.dimm else "needs dmidecode (root)",
        }


class FanReader:
    """Motherboard fan headers. A header is shown once it has reported a non-zero speed."""

    def __init__(self, chips: list[Chip], exclude: Chip | None = None):
        self.fans = [ch for c in chips if c is not exclude and c.name != "amdgpu"
                     for ch in c.all("fan")]
        self._peak: dict[int, float] = {}
        self._seen: set[int] = set()

    def read(self) -> list[dict]:
        out = []
        for i, ch in enumerate(self.fans):
            rpm = ch.value()
            if rpm:
                self._seen.add(i)
                self._peak[i] = max(self._peak.get(i, 0), rpm)
            if i not in self._seen:
                continue
            # Without a reported max, a typical case/CPU fan ceiling keeps bars comparable.
            top = ch.attr("max") or max(self._peak.get(i, 0), 2200)
            out.append({
                "name": ch.label or f"Fan #{ch.index}",
                "rpm": rpm,
                "text": f"{rpm:.0f} RPM" if rpm is not None else "N/A",
                "frac": min(1.0, (rpm or 0) / top),
            })
        return out


class DriveReader:
    def __init__(self, chips: list[Chip]):
        self.drives = []
        for c in by_name(chips, "nvme", "drivetemp"):
            ch = c.find("temp", "Composite") or c.find("temp")
            if ch:
                name = read_text(f"{c.device}/model") if c.device else None
                self.drives.append((name or c.name, ch, ch.attr("max")))

    def read(self) -> list[dict]:
        return [{"name": name, "temp": ch.value(), "max": warn / 1000 if warn else None}
                for name, ch, warn in self.drives]
