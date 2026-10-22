"""CPU metrics: temperature, load, clocks, package power and core voltage."""
from __future__ import annotations

import glob
import os
import time

from .hwmon import Channel, Chip, by_name, read_int, read_text

# Chip driver -> labels to try, best first.
_TEMP_SOURCES = [
    ("zenpower", ("Tdie", "Tctl")),
    ("k10temp", ("Tdie", "Tctl")),
    ("coretemp", ("Package id 0",)),
    ("cpu_thermal", ()),
    ("acpitz", ()),
]

_VCORE_LABELS = ("SVI2_Core", "Vcore", "CPU Vcore", "CPU Core", "VCORE", "CPUVCORE")

# Super I/O chips whose Vcore input is unlabeled; index follows the usual board wiring.
_VCORE_GUESS = {
    "nct6687": 2, "nct6683": 0,
    "nct6775": 0, "nct6776": 0, "nct6779": 0, "nct6791": 0, "nct6792": 0,
    "nct6793": 0, "nct6795": 0, "nct6796": 0, "nct6797": 0, "nct6798": 0, "nct6799": 0,
    "it87": 0, "it8620": 0, "it8628": 0, "it8665": 0, "it8686": 0, "it8688": 0,
    "it8689": 0, "it8792": 0,
}

_CPU_DIR = "/sys/devices/system/cpu"
_RAPL_GLOB = "/sys/class/powercap/intel-rapl:[0-9]*"


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith(("model name", "Model")):
                    return " ".join(line.split(":", 1)[1].split())
    except OSError:
        pass
    return "Unknown CPU"


def _read_proc_stat() -> dict[str, tuple[int, int]]:
    """{'cpu': (idle, total), 'cpu0': ...} in jiffies."""
    out = {}
    with open("/proc/stat") as f:
        for line in f:
            if not line.startswith("cpu"):
                break
            parts = line.split()
            vals = [int(v) for v in parts[1:9]]  # guest time is already counted in user
            idle = vals[3] + vals[4]  # idle + iowait
            out[parts[0]] = (idle, sum(vals))
    return out


class Rapl:
    """Package power from the powercap energy counters (Intel and AMD Zen)."""

    def __init__(self):
        self.domains = [d for d in sorted(glob.glob(_RAPL_GLOB))
                        if (read_text(f"{d}/name") or "").startswith("package")]
        self.available = bool(self.domains)
        self.denied = self.available and not all(os.access(f"{d}/energy_uj", os.R_OK)
                                                 for d in self.domains)
        self._ranges = [read_int(f"{d}/max_energy_range_uj") or 2**32 for d in self.domains]
        self._last: tuple[float, list[int]] | None = None

    def read(self) -> float | None:
        if not self.available or self.denied:
            return None
        now = time.monotonic()
        energies = [read_int(f"{d}/energy_uj") for d in self.domains]
        if any(e is None for e in energies):
            return None
        last, self._last = self._last, (now, energies)
        if last is None or now <= last[0]:
            return None
        joules = 0.0
        for e, prev, rng in zip(energies, last[1], self._ranges):
            delta = e - prev
            if delta < 0:  # counter wrapped
                delta += rng
            joules += delta / 1e6
        return joules / (now - last[0])


class CpuReader:
    def __init__(self, chips: list[Chip]):
        self.name = cpu_model()
        self.temp = self._pick_temp(chips)
        self.voltage, self.voltage_estimated = self._pick_vcore(chips)
        self.rapl = Rapl()
        # cpu0 usually has no `online` file; it can't be taken offline.
        self.cpus = sorted(int(os.path.basename(p)[3:]) for p in glob.glob(f"{_CPU_DIR}/cpu[0-9]*")
                           if read_text(f"{p}/online") in (None, "1"))
        self._freq_files = [self._freq_file(n) for n in self.cpus]
        self._prev_stat = _read_proc_stat()

    @staticmethod
    def _pick_temp(chips: list[Chip]) -> Channel | None:
        for driver, labels in _TEMP_SOURCES:
            for chip in by_name(chips, driver):
                ch = chip.find("temp", *labels) if labels else chip.find("temp")
                if ch:
                    return ch
        return None

    @staticmethod
    def _pick_vcore(chips: list[Chip]) -> tuple[Channel | None, bool]:
        for chip in chips:
            ch = chip.find("in", *_VCORE_LABELS)
            if ch:
                return ch, False
        for chip in chips:
            idx = _VCORE_GUESS.get(chip.name)
            if idx is None:
                continue
            for ch in chip.all("in"):
                if ch.index == idx:
                    return ch, True
        return None, False

    @staticmethod
    def _freq_file(n: int) -> str | None:
        # cpuinfo_avg_freq is the measured average (APERF/MPERF); scaling_cur_freq is the request.
        for name in ("cpuinfo_avg_freq", "scaling_cur_freq"):
            path = f"{_CPU_DIR}/cpu{n}/cpufreq/{name}"
            if read_int(path) is not None:
                return path
        return None

    def _loads(self) -> tuple[float | None, dict[str, float]]:
        cur = _read_proc_stat()
        prev, self._prev_stat = self._prev_stat, cur
        loads = {}
        for key, (idle, total) in cur.items():
            if key not in prev:
                continue
            d_total = total - prev[key][1]
            d_idle = idle - prev[key][0]
            loads[key] = 100.0 * (1 - d_idle / d_total) if d_total > 0 else 0.0
        return loads.pop("cpu", None), loads

    def read(self) -> dict:
        total_load, per_cpu = self._loads()
        cores = []
        mhz_values = []
        for n, path in zip(self.cpus, self._freq_files):
            khz = read_int(path) if path else None
            mhz = khz / 1000 if khz else None
            if mhz:
                mhz_values.append(mhz)
            cores.append({"id": n, "load": per_cpu.get(f"cpu{n}"), "mhz": mhz})

        power = self.rapl.read()
        voltage = self.voltage.value() if self.voltage else None
        current = power / voltage if power is not None and voltage and voltage > 0.3 else None
        return {
            "name": self.name,
            "temp": self.temp.value() if self.temp else None,
            "temp_source": f"{self.temp.chip.name} {self.temp.label or ''}".strip() if self.temp else None,
            "load": total_load,
            "mhz": sum(mhz_values) / len(mhz_values) if mhz_values else None,
            "power": power,
            "power_hint": "needs RAPL read access" if self.rapl.denied else None,
            "voltage": voltage,
            "voltage_estimated": self.voltage_estimated,
            "current": current,
            "cores": cores,
        }
