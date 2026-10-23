"""amdgpu controls written by rankine-tuned: power limit, performance level and profile, fan PWM.

Every value is validated against what the driver itself advertises before it is written.
"""
from __future__ import annotations

import glob
import os
import re

from ..sensors.hwmon import read_int, read_text

LEVELS = ("auto", "low", "high")  # "manual" and the profile_* levels belong to overdrive and profiling
FAN_AUTO, FAN_MANUAL = 2, 1


def drm_devices():
    """(card name, device path, driver, hwmon path) for each GPU, skipping connectors and duplicates."""
    seen = set()
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        if "-" in os.path.basename(card):
            continue  # connectors such as card1-DP-1
        dev = os.path.realpath(f"{card}/device")
        driver = os.path.basename(os.path.realpath(f"{dev}/driver")) if os.path.exists(f"{dev}/driver") else None
        if dev in seen or driver in (None, "simpledrm", "virtio-pci"):
            continue
        seen.add(dev)
        hwmon = next(iter(sorted(glob.glob(f"{dev}/hwmon/hwmon*"))), None)
        yield os.path.basename(card), dev, driver, hwmon


def parse_profiles(text: str) -> tuple[list[tuple[int, str]], int | None]:
    """[(index, name)] and the active index from pp_power_profile_mode."""
    profiles, active = [], None
    for m in re.finditer(r"^\s*(\d+)\s+([A-Z0-9_]+)\s*(\*?)\s*:", text, re.M):
        profiles.append((int(m.group(1)), m.group(2)))
        if m.group(3):
            active = int(m.group(1))
    return profiles, active


class TuningError(Exception):
    pass


def _write(path: str, value) -> None:
    try:
        with open(path, "w") as f:
            f.write(f"{value}\n")
    except OSError as e:
        raise TuningError(f"cannot write {os.path.basename(path)}: {e.strerror or e}") from e


class AmdGpuControl:
    def __init__(self, card: str, dev: str, hwmon: str):
        self.card, self.dev, self.hwmon = card, dev, hwmon
        self.edge = self._temp_input("edge")
        self.junction = self._temp_input("junction")

    def _temp_input(self, label: str) -> str | None:
        for path in glob.glob(f"{self.hwmon}/temp*_label"):
            if read_text(path) == label:
                return path.replace("_label", "_input")
        return None

    # ── reads ──
    def power(self) -> dict | None:
        cap = read_int(f"{self.hwmon}/power1_cap")
        if cap is None:
            return None
        return {"cap": cap / 1e6,
                "min": (read_int(f"{self.hwmon}/power1_cap_min") or cap) / 1e6,
                "max": (read_int(f"{self.hwmon}/power1_cap_max") or cap) / 1e6,
                "default": (read_int(f"{self.hwmon}/power1_cap_default") or cap) / 1e6}

    def level(self) -> str | None:
        return read_text(f"{self.dev}/power_dpm_force_performance_level")

    def profiles(self) -> tuple[list[tuple[int, str]], int | None]:
        return parse_profiles(read_text(f"{self.dev}/pp_power_profile_mode") or "")

    def fan_mode(self) -> int | None:
        return read_int(f"{self.hwmon}/pwm1_enable")

    def fan_percent(self) -> float | None:
        pwm = read_int(f"{self.hwmon}/pwm1")
        top = read_int(f"{self.hwmon}/pwm1_max") or 255
        return 100 * pwm / top if pwm is not None else None

    def temps(self) -> tuple[float | None, float | None]:
        edge = read_int(self.edge) if self.edge else None
        junction = read_int(self.junction) if self.junction else None
        return (edge / 1000 if edge is not None else None,
                junction / 1000 if junction is not None else None)

    def snapshot(self) -> dict:
        """Raw values that restore() can put back."""
        _, profile = self.profiles()
        return {"power_uw": read_int(f"{self.hwmon}/power1_cap"), "level": self.level(),
                "profile": profile}

    # ── writes ──
    def set_power(self, watts: float) -> None:
        p = self.power()
        if p is None:
            raise TuningError("this card has no power limit control")
        if not p["min"] - 0.5 <= watts <= p["max"] + 0.5:
            raise TuningError(f"power limit must be between {p['min']:.0f} and {p['max']:.0f} W")
        _write(f"{self.hwmon}/power1_cap", int(round(watts)) * 1_000_000)

    def set_level(self, level: str) -> None:
        if level not in LEVELS:
            raise TuningError(f"unknown performance level {level!r}")
        _write(f"{self.dev}/power_dpm_force_performance_level", level)

    def set_profile(self, index: int) -> None:
        profiles, _ = self.profiles()
        names = dict(profiles)
        if index not in names or names[index] == "CUSTOM":
            raise TuningError(f"unknown power profile {index}")
        _write(f"{self.dev}/pp_power_profile_mode", index)

    def set_fan_auto(self) -> None:
        _write(f"{self.hwmon}/pwm1_enable", FAN_AUTO)

    def set_fan_percent(self, percent: float) -> None:
        top = read_int(f"{self.hwmon}/pwm1_max") or 255
        if self.fan_mode() != FAN_MANUAL:
            _write(f"{self.hwmon}/pwm1_enable", FAN_MANUAL)
        _write(f"{self.hwmon}/pwm1", int(round(max(0.0, min(100.0, percent)) * top / 100)))

    def restore(self, snap: dict) -> None:
        """Puts back a snapshot; keeps going past individual failures and reports the first one."""
        writes = []
        if snap.get("power_uw") is not None:
            writes.append((f"{self.hwmon}/power1_cap", snap["power_uw"]))
        if snap.get("level") in LEVELS:
            writes.append((f"{self.dev}/power_dpm_force_performance_level", snap["level"]))
        if snap.get("profile") is not None:
            writes.append((f"{self.dev}/pp_power_profile_mode", snap["profile"]))
        errors = []
        for path, value in writes:
            try:
                _write(path, value)
            except TuningError as e:
                errors.append(str(e))
        if errors:
            raise TuningError(errors[0])


def amd_controls() -> dict[str, AmdGpuControl]:
    return {card: AmdGpuControl(card, dev, hwmon)
            for card, dev, driver, hwmon in drm_devices() if driver == "amdgpu" and hwmon}
