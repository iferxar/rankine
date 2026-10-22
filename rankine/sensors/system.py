"""Memory, fans and drive temperatures."""
from __future__ import annotations

import json
import os
import re
import subprocess

from .hwmon import Chip, by_name, read_text
from .spd import read_modules

GIB = 1024 ** 3
DMI_CACHE = os.path.expanduser("~/.cache/rankine/dimm.json")
DMIDECODE_CMD = ["dmidecode", "-t", "17"]


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


def _fingerprint(modules: list[dict]) -> list[str]:
    """Identifies the installed DIMMs so a cached BIOS reading is dropped after a RAM swap."""
    return sorted(f"{m['vendor']}:{m['part']}:{m['size_gb']}" for m in modules)


def save_dimm_cache(dmidecode_output: str, modules: list[dict]) -> bool:
    info = parse_dmidecode(dmidecode_output)
    if not info:
        return False
    os.makedirs(os.path.dirname(DMI_CACHE), exist_ok=True)
    with open(DMI_CACHE, "w") as f:
        json.dump({**info, "modules": _fingerprint(modules)}, f)
    return True


def load_dimm_info(modules: list[dict]) -> dict:
    """Configured DIMM speed/voltage: live when running as root, else the cache from a past detect."""
    if os.geteuid() == 0:
        try:
            res = subprocess.run(DMIDECODE_CMD, capture_output=True, text=True, timeout=3)
            info = parse_dmidecode(res.stdout) if res.returncode == 0 else {}
            if info:
                return info
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        with open(DMI_CACHE) as f:
            cached = json.load(f)
    except (OSError, ValueError):
        return {}
    if modules and cached.get("modules") != _fingerprint(modules):
        return {}
    return cached


def _summarize(modules: list[dict]) -> dict:
    if not modules:
        return {"modules": None, "mem_type": None, "part": None, "rated_clock": None, "rated_cl": None,
                "rated_voltage": None, "rated_profile": None}
    first = modules[0]
    sizes = {m["size_gb"] for m in modules}
    count = f"{len(modules)} × {first['size_gb']:g} GB" if len(sizes) == 1 \
        else " + ".join(f"{m['size_gb']:g}" for m in modules) + " GB"
    xmp = first["xmp"]
    return {
        "modules": count,
        "mem_type": first["type"],
        "part": " ".join(p for p in (first["vendor"], first["part"]) if p) or None,
        "rated_clock": xmp["mts"] if xmp else first["jedec_mts"],
        "rated_cl": xmp["cl"] if xmp else first["jedec_cl"],
        "rated_voltage": xmp["voltage"] if xmp else None,
        "rated_profile": "XMP" if xmp else "JEDEC",
    }


class MemoryReader:
    def __init__(self, chips: list[Chip]):
        self.temps = [c.find("temp") for c in by_name(chips, "spd5118", "jc42") if c.find("temp")]
        self.modules = read_modules()
        self.summary = _summarize(self.modules)
        self.reload_dimm_info()

    def reload_dimm_info(self):
        self.dimm = load_dimm_info(self.modules)

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
            "cached": (m.get("Cached", 0) + m.get("Buffers", 0)) / GIB,
            "clock": self.dimm.get("clock"),
            "voltage": self.dimm.get("voltage"),
            "dimm_detected": bool(self.dimm),
            "temp": max(temps) if temps else None,
            **self.summary,
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
