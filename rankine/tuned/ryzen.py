"""AMD Ryzen tuning through the ryzen_smu kernel module: PM table readings, PBO limits, Curve Optimizer.

Only Zen 3 desktop (Vermeer) is enabled: its command IDs and PM table layouts are community
reverse-engineered (ryzen_smu, ZenStates-Core, ryzen_monitor), not documented by AMD, so every
other family stays read-only until someone verifies it on hardware.
"""
from __future__ import annotations

import glob
import os
import struct

from .gpu import TuningError

SMU_DIR = "/sys/kernel/ryzen_smu_drv"
VERMEER = 12  # ryzen_smu codename index

# Mailbox commands for Vermeer.
RSMU_SET_PPT, RSMU_SET_TDC, RSMU_SET_EDC = 0x53, 0x54, 0x55  # mW, mA, mA
RSMU_GET_CO = 0x7C                                           # arg: core mask -> margin
MP1_SET_CO, MP1_SET_CO_ALL = 0x35, 0x36                      # arg: core mask | margin

STATUS = {0x01: "ok", 0xFF: "failed", 0xFE: "unknown command", 0xFD: "rejected: prerequisite unmet",
          0xFC: "rejected: busy", 0xFB: "timeout", 0xFA: "invalid argument",
          0xF9: "unsupported platform"}

CO_RANGE = (-30, 0)  # Zen 3 accepts -30..30; Rankine only offers the undervolting half

# Float indices into the PM table. Limits and package values share positions across Vermeer
# tables; the per-core blocks move between versions.
_COMMON = {"ppt_limit": 0, "ppt": 1, "tdc_limit": 2, "tdc": 3, "thm": 5, "edc_limit": 8, "edc": 9,
           "socket_power": 29}
LAYOUTS = {
    0x380804: {**_COMMON, "cores": 16, "core_power": 169, "core_voltage": 185, "core_freq": 265,
               "core_c0": 281},
    0x380805: {**_COMMON, "cores": 16, "core_power": 172, "core_voltage": 188, "core_freq": 268,
               "core_c0": 284},
    0x380904: {**_COMMON, "cores": 8, "core_power": 169, "core_voltage": 177, "core_freq": 217,
               "core_c0": 225},
    0x380905: {**_COMMON, "cores": 8, "core_power": 172, "core_voltage": 180, "core_freq": 220,
               "core_c0": 228},
}


def _read_u(path: str, size: int) -> int | None:
    try:
        with open(path, "rb") as f:
            data = f.read(size)
    except OSError:
        return None
    return int.from_bytes(data, "little") if len(data) == size else None


def ccd_layout() -> list[list[int]]:
    """Physical cores grouped by CCD (one L3 per CCD on Zen 3), in OS order: [[0..7], [8..15]]."""
    groups: dict[str, set[int]] = {}
    for cpu in glob.glob("/sys/devices/system/cpu/cpu[0-9]*"):
        try:
            with open(f"{cpu}/cache/index3/shared_cpu_list") as f:
                l3 = f.read().strip()
            with open(f"{cpu}/topology/core_id") as f:
                core = int(f.read())
        except (OSError, ValueError):
            continue
        groups.setdefault(l3, set()).add(core)
    return [sorted(g) for g in sorted(groups.values(), key=min)]


class RyzenSmu:
    """Thin wrapper over the ryzen_smu sysfs files. Tests replace _command and _pm_raw."""

    def __init__(self, path: str = SMU_DIR, ccds: list[list[int]] | None = None):
        self.path = path
        self.ccds = ccd_layout() if ccds is None else ccds

    @property
    def available(self) -> bool:
        return os.path.isdir(self.path)

    def codename(self) -> int | None:
        try:
            with open(f"{self.path}/codename") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def driver_version(self) -> str | None:
        try:
            with open(f"{self.path}/drv_version") as f:
                return f.read().strip()
        except OSError:
            return None

    def table_version(self) -> int | None:
        return _read_u(f"{self.path}/pm_table_version", 4)

    def _pm_raw(self) -> bytes:
        with open(f"{self.path}/pm_table", "rb") as f:
            return f.read()

    def _command(self, mailbox: str, command: int, args: list[int]) -> tuple[int, list[int]]:
        """Runs one SMU request; returns (status, six result words)."""
        with open(f"{self.path}/smu_args", "wb") as f:
            f.write(struct.pack("<6I", *(args + [0] * 6)[:6]))
        cmd_file = f"{self.path}/{'rsmu_cmd' if mailbox == 'rsmu' else 'mp1_smu_cmd'}"
        with open(cmd_file, "wb") as f:
            f.write(struct.pack("<I", command))
        status = _read_u(cmd_file, 4) or 0
        with open(f"{self.path}/smu_args", "rb") as f:
            result = list(struct.unpack("<6I", f.read(24)))
        return status, result

    def command(self, mailbox: str, command: int, args: list[int]) -> list[int]:
        try:
            status, result = self._command(mailbox, command, args)
        except OSError as e:
            raise TuningError(f"SMU request failed: {e.strerror or e}") from e
        if status != 0x01:
            raise TuningError(f"SMU {mailbox} command {command:#x}: {STATUS.get(status, hex(status))}")
        return result

    # ── PM table ──
    def pm_table(self) -> dict | None:
        """Named readings from the PM table, or None when the layout is unknown or looks wrong."""
        layout = LAYOUTS.get(self.table_version() or 0)
        if layout is None:
            return None
        raw = self._pm_raw()
        values = struct.unpack(f"<{len(raw) // 4}f", raw[: len(raw) // 4 * 4])

        def at(i):
            return values[i] if i < len(values) else None

        n = min(layout["cores"], sum(len(c) for c in self.ccds) or layout["cores"])
        out = {k: at(i) for k, i in layout.items() if k not in ("cores",) and not k.startswith("core_")}
        for key in ("core_power", "core_voltage", "core_freq", "core_c0"):
            out[key] = [at(layout[key] + i) for i in range(n)]
        # Sanity check: a wrong layout produces absurd numbers long before it produces plausible ones.
        if not (10 <= (out["ppt_limit"] or 0) <= 1000 and 1 <= (out["tdc_limit"] or 0) <= 1000
                and all(v is not None and 0 <= v <= 2.0 for v in out["core_voltage"])):
            return None
        out["core_freq"] = [f * 1000 if f is not None and f < 20 else f for f in out["core_freq"]]  # GHz
        return out

    # ── Curve Optimizer ──
    def core_mask(self, core: int) -> int:
        """Mask for the core's CCD and index within it, as the SMU expects on Zen 3."""
        for ccd, cores in enumerate(self.ccds):
            if core in cores:
                return (ccd << 28) | ((cores.index(core) % 8) << 20)
        raise TuningError(f"unknown core {core}")

    @property
    def all_cores(self) -> list[int]:
        return [c for ccd in self.ccds for c in ccd]

    def per_core_co_supported(self) -> bool:
        """With cores fused off, OS order no longer matches the SMU's physical index; only allow
        per-core margins when every CCD is complete."""
        return bool(self.ccds) and all(len(c) == 8 for c in self.ccds)

    def get_co(self, core: int) -> int:
        result = self.command("rsmu", RSMU_GET_CO, [self.core_mask(core)])
        margin = result[0] & 0xFFFF
        margin = margin - 0x10000 if margin & 0x8000 else margin
        if not -50 <= margin <= 50:
            raise TuningError(f"implausible Curve Optimizer reading {margin} for core {core}")
        return margin

    def set_co(self, core: int, margin: int) -> None:
        lo, hi = CO_RANGE
        if not lo <= margin <= hi:
            raise TuningError(f"Curve Optimizer margin must be between {lo} and {hi}")
        self.command("mp1", MP1_SET_CO, [self.core_mask(core) | (margin & 0xFFFF)])

    # ── PBO limits ──
    def set_limits(self, ppt_w: float | None = None, tdc_a: float | None = None,
                   edc_a: float | None = None) -> None:
        for value, cmd in ((ppt_w, RSMU_SET_PPT), (tdc_a, RSMU_SET_TDC), (edc_a, RSMU_SET_EDC)):
            if value is not None:
                self.command("rsmu", cmd, [int(round(value * 1000))])


class RyzenControl:
    """The CPU as one tunable device, with the snapshot/restore shape the service uses for GPUs."""

    def __init__(self, smu: RyzenSmu):
        self.smu = smu
        self._co_cache: list[int] | None = None  # margins only change through this class
        self.co_readable = False
        self.co_error = ""
        try:
            self.smu.get_co(self.smu.all_cores[0])
            self.co_readable = True
        except (TuningError, IndexError) as e:
            self.co_error = str(e)
        table = self.smu.pm_table()
        self.boot_limits = ({k: table[k] for k in ("ppt_limit", "tdc_limit", "edc_limit")}
                            if table else None)

    def limit_ranges(self) -> dict | None:
        """Lowering is always allowed; raising up to 1.5 times the limits found at startup."""
        if not self.boot_limits:
            return None
        return {"ppt": [45, round(self.boot_limits["ppt_limit"] * 1.5)],
                "tdc": [30, round(self.boot_limits["tdc_limit"] * 1.5)],
                "edc": [30, round(self.boot_limits["edc_limit"] * 1.5)]}

    def curve(self) -> list[int] | None:
        if not self.co_readable:
            return None
        if self._co_cache is None:
            self._co_cache = [self.smu.get_co(c) for c in self.smu.all_cores]
        return list(self._co_cache)

    def snapshot(self) -> dict:
        table = self.smu.pm_table() or {}
        return {"ppt": table.get("ppt_limit"), "tdc": table.get("tdc_limit"), "edc": table.get("edc_limit"),
                "co": self.curve()}

    def set_limits(self, ppt: float | None = None, tdc: float | None = None, edc: float | None = None):
        ranges = self.limit_ranges()
        if ranges is None:
            raise TuningError("PBO limits need a readable PM table")
        for name, value in (("ppt", ppt), ("tdc", tdc), ("edc", edc)):
            if value is not None and not ranges[name][0] <= value <= ranges[name][1]:
                unit = "W" if name == "ppt" else "A"
                raise TuningError(f"{name.upper()} must be between {ranges[name][0]} and {ranges[name][1]} {unit}")
        self.smu.set_limits(ppt, tdc, edc)

    def set_curve(self, margins: list[int]) -> None:
        if not self.co_readable:
            raise TuningError("Curve Optimizer is off: the current margins cannot be read back "
                              f"({self.co_error}), so they could not be restored")
        cores = self.smu.all_cores
        if len(margins) != len(cores):
            raise TuningError(f"expected {len(cores)} margins")
        if len(set(margins)) > 1 and not self.smu.per_core_co_supported():
            raise TuningError("per-core margins need every core enabled; use one margin for all")
        lo, hi = CO_RANGE
        if not all(lo <= m <= hi for m in margins):
            raise TuningError(f"Curve Optimizer margins must be between {lo} and {hi}")
        current = self.curve()
        try:
            for core, margin, now in zip(cores, margins, current):
                if margin != now:
                    self.smu.set_co(core, margin)
        finally:
            self._co_cache = None

    def restore(self, snap: dict) -> None:
        now = self.snapshot()
        if any(snap.get(k) is not None and round(snap[k]) != round(now.get(k) or 0) for k in ("ppt", "tdc", "edc")):
            self.smu.set_limits(snap.get("ppt"), snap.get("tdc"), snap.get("edc"))
        if snap.get("co") is not None and snap["co"] != now.get("co"):
            # Restoring may need positive margins the BIOS set; the UI range does not apply here.
            try:
                for core, margin, current in zip(self.smu.all_cores, snap["co"], now["co"] or []):
                    if margin != current:
                        self.smu.command("mp1", MP1_SET_CO, [self.smu.core_mask(core) | (margin & 0xFFFF)])
            finally:
                self._co_cache = None

    def risky(self, boot: dict) -> bool:
        """Limits above the startup ones, or more undervolt than at startup: needs a stability test."""
        now = self.snapshot()
        if any((now.get(k) or 0) > (boot.get(k) or 0) + 0.5 for k in ("ppt", "tdc", "edc")):
            return True
        return any(n < b for n, b in zip(now.get("co") or [], boot.get("co") or []))


def ryzen_control(path: str = SMU_DIR) -> RyzenControl | None:
    """The CPU control when ryzen_smu is loaded on a verified family with a known PM table."""
    smu = RyzenSmu(path)
    try:
        if not smu.available or smu.codename() != VERMEER or smu.pm_table() is None:
            return None
        return RyzenControl(smu)
    except (OSError, TuningError):
        return None
