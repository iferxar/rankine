"""Discovery of Linux hwmon sensor chips under /sys/class/hwmon."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

HWMON_ROOT = "/sys/class/hwmon"

_CHANNEL_RE = re.compile(r"^(temp|fan|in|power|curr|freq)(\d+)_(input|average)$")

# hwmon raw units -> °C, V, RPM, W, A, MHz
_SCALE = {"temp": 1e-3, "in": 1e-3, "fan": 1.0, "power": 1e-6, "curr": 1e-3, "freq": 1e-6}


def read_text(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def read_int(path: str) -> int | None:
    text = read_text(path)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _natural_key(name: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name)]


@dataclass(eq=False)
class Channel:
    chip: "Chip"
    kind: str
    index: int
    path: str
    label: str | None

    def value(self) -> float | None:
        raw = read_int(self.path)
        return None if raw is None else raw * _SCALE[self.kind]

    def attr(self, suffix: str) -> int | None:
        return read_int(f"{self.chip.path}/{self.kind}{self.index}_{suffix}")


@dataclass(eq=False)
class Chip:
    name: str
    path: str
    device: str | None
    channels: list[Channel] = field(default_factory=list)

    def all(self, kind: str) -> list[Channel]:
        return [c for c in self.channels if c.kind == kind]

    def find(self, kind: str, *labels: str) -> Channel | None:
        """First channel of `kind` whose label matches one of `labels` (case-insensitive),
        tried in order. With no labels, the lowest-numbered channel."""
        candidates = self.all(kind)
        if not labels:
            return candidates[0] if candidates else None
        for wanted in labels:
            for c in candidates:
                if c.label and c.label.lower() == wanted.lower():
                    return c
        return None


def discover(root: str = HWMON_ROOT) -> list[Chip]:
    chips: list[Chip] = []
    try:
        entries = sorted(os.listdir(root), key=_natural_key)
    except OSError:
        return chips
    for entry in entries:
        path = os.path.join(root, entry)
        dev_link = os.path.join(path, "device")
        chip = Chip(
            name=read_text(os.path.join(path, "name")) or entry,
            path=path,
            device=os.path.realpath(dev_link) if os.path.exists(dev_link) else None,
        )
        found: dict[tuple[str, int], str] = {}
        for fname in os.listdir(path):
            m = _CHANNEL_RE.match(fname)
            if not m:
                continue
            key = (m.group(1), int(m.group(2)))
            # Prefer *_input over *_average when a channel exposes both.
            if key not in found or m.group(3) == "input":
                found[key] = fname
        for (kind, idx), fname in sorted(found.items()):
            label = read_text(os.path.join(path, f"{kind}{idx}_label"))
            chip.channels.append(Channel(chip, kind, idx, os.path.join(path, fname), label))
        chips.append(chip)
    return chips


def by_name(chips: list[Chip], *names: str) -> list[Chip]:
    return [c for c in chips if c.name in names]
