"""DIMM details from the SPD EEPROMs (ee1004 for DDR4, spd5118 for DDR5), readable without root."""
from __future__ import annotations

import glob
import math
import os

from .hwmon import read_text

# JEP106 manufacturer codes as stored in SPD (bank byte with parity stripped, code byte).
_VENDORS = {
    (0x02, 0x9E): "Corsair", (0x04, 0xCD): "G.Skill", (0x01, 0x98): "Kingston",
    (0x05, 0x9B): "Crucial", (0x00, 0xCE): "Samsung", (0x00, 0xAD): "SK hynix",
    (0x00, 0x2C): "Micron", (0x04, 0xEF): "TeamGroup", (0x04, 0xCB): "ADATA",
    (0x06, 0x02): "Patriot", (0x03, 0x0B): "Nanya", (0x05, 0x10): "Lexar",
}

_STANDARD_SPEEDS = [1600, 1866, 2133, 2400, 2666, 2933, 3000, 3200, 3333, 3466, 3600, 3733,
                    3866, 4000, 4133, 4266, 4400, 4600, 4800, 5200, 5600, 6000, 6400, 6800,
                    7200, 7600, 8000, 8400, 8800]


def _s8(b: int) -> int:
    return b - 256 if b > 127 else b


def _mts(tck_ps: int) -> int | None:
    if tck_ps <= 0:
        return None
    raw = 2e6 / tck_ps
    nearest = min(_STANDARD_SPEEDS, key=lambda s: abs(s - raw))
    return nearest if abs(nearest - raw) / raw < 0.01 else round(raw)


def _cl(taa_ps: int, tck_ps: int) -> int:
    # JEDEC rounding: nCK = floor(tAA / tCK + 0.974)
    return math.floor(taa_ps / tck_ps + 0.974)


def _vendor(bank: int, code: int) -> str | None:
    return _VENDORS.get((bank & 0x7F, code))


def parse_ddr4(d: bytes) -> dict:
    tck = d[18] * 125 + _s8(d[125])
    taa = d[24] * 125 + _s8(d[123])
    density_mb = 256 << (d[4] & 0x0F)
    width = 4 << (d[12] & 0x07)
    ranks = ((d[12] >> 3) & 0x07) + 1
    bus = 8 << (d[13] & 0x07)
    module = {
        "type": "DDR4",
        "size_gb": density_mb / 8 * bus / width * ranks / 1024,
        "jedec_mts": _mts(tck),
        "jedec_cl": _cl(taa, tck),
        "vendor": _vendor(d[320], d[321]),
        "part": d[329:349].decode("ascii", "replace").strip() or None,
        "xmp": None,
    }
    # XMP 2.0: magic 0x0C 0x4A at 384, profile 1 enabled in bit 0 of 386, revision in 387.
    if len(d) >= 440 and d[384] == 0x0C and d[385] == 0x4A and d[386] & 1:
        xtck = d[396] * 125 + _s8(d[431])
        xtaa = d[401] * 125 + _s8(d[430])
        volt = d[393]
        module["xmp"] = {
            "mts": _mts(xtck),
            "cl": _cl(xtaa, xtck) if xtck > 0 else None,
            "voltage": (volt >> 7) + (volt & 0x7F) / 100,
        }
    return module


def parse_ddr5(d: bytes) -> dict:
    tck = int.from_bytes(d[20:22], "little")
    taa = int.from_bytes(d[30:32], "little")
    density_gb = {1: 4, 2: 8, 3: 12, 4: 16, 5: 24, 6: 32, 7: 48, 8: 64}.get(d[4] & 0x1F, 0)
    dies = ((d[4] >> 5) & 0x07) + 1
    width = 4 << ((d[6] >> 5) & 0x03)
    ranks = ((d[234] >> 3) & 0x07) + 1
    bus = 8 << (d[235] & 0x07)
    sub_channels = 2  # every DDR5 DIMM has two 32-bit sub-channels
    return {
        "type": "DDR5",
        "size_gb": density_gb * dies / 8 * bus / width * ranks * sub_channels,
        "jedec_mts": _mts(tck),
        "jedec_cl": _cl(taa, tck) if tck else None,
        "vendor": _vendor(d[512], d[513]) if len(d) > 513 else None,
        "part": (d[521:551].decode("ascii", "replace").strip() or None) if len(d) > 550 else None,
        "xmp": None,
    }


def _eeproms() -> list[str]:
    paths = []
    for dev in sorted(glob.glob("/sys/bus/i2c/devices/*")):
        if read_text(f"{dev}/name") in ("ee1004", "spd5118"):
            for candidate in (f"{dev}/eeprom", *glob.glob(f"{dev}/*/nvmem")):
                if os.path.exists(candidate):
                    paths.append(candidate)
                    break
    return paths


def read_modules() -> list[dict]:
    modules = []
    for path in _eeproms():
        try:
            with open(path, "rb") as f:
                data = f.read(1024)
        except OSError:
            continue
        if len(data) < 256:
            continue
        try:
            if data[2] == 0x0C:
                modules.append(parse_ddr4(data))
            elif data[2] == 0x12:
                modules.append(parse_ddr5(data))
        except IndexError:
            continue
    return modules
