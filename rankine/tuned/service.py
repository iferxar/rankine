"""rankine-tuned: the system service that applies GPU tuning on behalf of the UI.

Safety rules (docs/TUNING.md):
- every change must be confirmed within CONFIRM_SECONDS or it is reverted, by this service, not the UI;
- what the card looked like before Rankine touched it is kept in a baseline file and restored when
  the service stops, or by `rankine-tuned --reset` (ExecStopPost) if it crashed;
- at boot, only a profile the user saved is applied, and not after a session that applied it and
  then ended uncleanly (bootprofile.py);
- a GPU hang or reset in the kernel log puts every changed card back to its original clocks, voltage
  and power (the fan curve stays: it only adds cooling).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time

from PySide6.QtCore import ClassInfo, QCoreApplication, QObject, QTimer, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage

from .. import __version__
from .bus import BUS_NAME, INTERFACE, OBJECT_PATH
from .bootprofile import SYSTEM_STATE_DIR, BootProfile
from .fan import FanCurve
from .faults import KMSG, FaultWatcher
from .gpu import FAN_AUTO, VOLTAGE_OFFSET_RANGE, AmdGpuControl, TuningError, amd_controls
from .polkit import Authorizer
from .probe import probe
from .ryzen import CO_RANGE, LAYOUTS, MP1_SET_CO, RyzenControl, RyzenSmu, ryzen_control

CONFIRM_SECONDS = 15
FAN_INTERVAL_MS = 1000
MAX_FAULTS = 20
SYSTEM_RUNTIME_DIR = "/run/rankine-tuned"
_FAN_MODE_NAMES = {0: "full", 1: "manual", 2: "auto"}


def log(text: str) -> None:
    print(f"rankine-tuned: {text}", file=sys.stderr, flush=True)


class CardState:
    """Everything needed to put a card back: driver values plus the software fan curve, if any."""

    def __init__(self, snap: dict, fan_points):
        self.snap, self.fan_points = snap, fan_points

    def to_json(self):
        return {"snap": self.snap, "fan_points": self.fan_points}

    @classmethod
    def from_json(cls, data):
        return cls(data["snap"], data.get("fan_points"))


@ClassInfo({"D-Bus Interface": INTERFACE})
class Tuned(QObject):
    def __init__(self, bus: QDBusConnection, authorizer: Authorizer, runtime_dir: str,
                 controls: dict[str, AmdGpuControl] | None = None, kmsg: str = KMSG,
                 state_dir: str = SYSTEM_STATE_DIR, cpu: RyzenControl | None | str = "detect"):
        super().__init__()
        self.bus = bus
        self.auth = authorizer
        self.baseline_path = os.path.join(runtime_dir, "baseline.json")
        os.makedirs(runtime_dir, exist_ok=True)
        self.controls = amd_controls() if controls is None else controls  # GPUs
        self.cpu = ryzen_control() if cpu == "detect" else cpu
        # Everything with snapshot()/restore(): baselines, pending changes and the boot profile
        # treat the CPU as one more device, named "cpu".
        self.devices = {**self.controls, **({"cpu": self.cpu} if self.cpu else {})}
        self.fans: dict[str, FanCurve] = {}
        self.baseline: dict[str, CardState] = {}
        self.pending: dict | None = None  # {"owner", "items", "deadline", "undo": {card: CardState}}
        self.revert_timer = QTimer(self, singleShot=True)
        self.revert_timer.timeout.connect(self._expire)
        self.fan_timer = QTimer(self, interval=FAN_INTERVAL_MS)
        self.fan_timer.timeout.connect(self._drive_fans)
        # Values when the service started, i.e. at boot: the "default" the UI offers to go back to.
        self.boot = {card: c.snapshot() for card, c in self.devices.items()}
        self.faults: list[dict] = []
        self.fault_count = 0
        self.watcher = FaultWatcher(self._on_fault, kmsg)
        if not self.watcher.available:
            log(f"hang detection off: {self.watcher.error}")
        self.profile = BootProfile(state_dir)
        self.profile.start_session()
        self._apply_boot_profile()

    # ── state helpers ──
    def _state(self, card: str) -> CardState:
        curve = self.fans.get(card)
        return CardState(self.devices[card].snapshot(), [list(p) for p in curve.points] if curve else None)

    def _restore(self, card: str, state: CardState) -> None:
        try:
            self.devices[card].restore(state.snap)
        finally:
            if card in self.controls:
                self._set_fan(card, state.fan_points)

    def _set_fan(self, card: str, points) -> None:
        if points is None:
            if self.fans.pop(card, None) is not None or self.controls[card].fan_mode() != FAN_AUTO:
                self.controls[card].set_fan_auto()
        else:
            self.fans[card] = FanCurve(points)
            self._drive_fans()
        if self.fans:
            self.fan_timer.start()
        else:
            self.fan_timer.stop()

    def _save_baseline(self) -> None:
        if self.baseline:
            with open(self.baseline_path, "w") as f:
                json.dump({card: s.to_json() for card, s in self.baseline.items()}, f)
        elif os.path.exists(self.baseline_path):
            os.remove(self.baseline_path)

    def _drive_fans(self) -> None:
        for card, curve in list(self.fans.items()):
            control = self.controls[card]
            edge, junction = control.temps()
            try:
                if edge is None:
                    raise TuningError("no temperature reading")
                previous = curve.current
                percent = curve.target(edge, junction)
                if previous is None or abs(percent - previous) >= 0.5 or control.fan_mode() != 1:
                    control.set_fan_percent(percent)
            except TuningError as e:
                log(f"{card} fan curve stopped ({e}); handing the fan back to firmware")
                self.fans.pop(card, None)
                try:
                    control.set_fan_auto()
                except TuningError as e2:
                    log(f"{card} cannot restore firmware fan control: {e2}")
        if not self.fans:
            self.fan_timer.stop()

    def restore_all(self) -> None:
        """Back to how the cards were before Rankine changed them (service shutdown)."""
        self.revert_timer.stop()
        self.pending = None
        for card, state in list(self.baseline.items()):
            try:
                self._restore(card, state)
                log(f"{card} restored to its original settings")
            except TuningError as e:
                log(f"{card} restore failed: {e}")
        self.baseline.clear()
        self._save_baseline()

    def _pending_json(self, sender: str | None) -> dict | None:
        if not self.pending:
            return None
        return {"items": self.pending["items"],
                "remaining": max(0.0, self.pending["deadline"] - time.monotonic()),
                "mine": sender == self.pending["owner"]}

    def _reply(self, msg: QDBusMessage, data: dict) -> None:
        self.bus.send(msg.createReply(json.dumps(data)))

    def _expire(self) -> None:
        if self.pending:
            log("change not confirmed in time; reverting " + "; ".join(self.pending["items"]))
            self._revert_pending()

    def _revert_pending(self) -> str | None:
        error = None
        for card, state in self.pending["undo"].items():
            try:
                self._restore(card, state)
            except TuningError as e:
                error = error or str(e)
                log(f"{card} revert failed: {e}")
                continue
            # Back to exactly how Rankine found it: nothing left to restore later.
            original = self.baseline.get(card)
            if original and original.to_json() == self._state(card).to_json():
                del self.baseline[card]
        self._save_baseline()
        self.pending = None
        self.revert_timer.stop()
        return error

    def _apply_boot_profile(self) -> None:
        if not self.profile.enabled:
            if self.profile.data.get("notice"):
                log("boot profile " + self.profile.data["notice"])
            return
        for card, data in self.profile.cards.items():
            if card not in self.devices:
                log(f"boot profile: {card} not found, skipped")
                continue
            before = self._state(card)
            try:
                self._restore(card, CardState.from_json(data))
            except (TuningError, ValueError) as e:
                try:
                    self._restore(card, before)
                except TuningError:
                    pass
                self.profile.disable(f"Not applied: {card} rejected it ({e}).")
                log(f"boot profile for {card} failed: {e}")
                continue
            self.baseline[card] = before
            log(f"{card} boot profile applied")
        self._save_baseline()
        if self.baseline:
            self.profile.mark_applied()

    def _risky(self, card: str) -> bool:
        """Above the boot power limit or clocks, or undervolted: needs a passed stability test."""
        if card == "cpu":
            return self.cpu.risky(self.boot["cpu"])
        now, boot = self.controls[card].snapshot(), self.boot[card]
        if (now["power_uw"] or 0) > (boot["power_uw"] or 0):
            return True
        n, b = now.get("od") or {}, boot.get("od") or {}
        return any((n.get(k) or 0) > (b.get(k) or 0) for k in ("sclk_max", "mclk_max")) \
            or (n.get("voltage_offset") or 0) < (b.get("voltage_offset") or 0)

    def _on_fault(self, text: str) -> None:
        self.fault_count += 1
        self.faults = (self.faults + [{"time": time.time(), "text": text}])[-MAX_FAULTS:]
        what = "CPU machine-check error" if "mce" in text.lower() or "machine check" in text.lower() \
            else "GPU hang"
        log(f"{what} in the kernel log: {text}")
        if self.profile.enabled and any(card in self.devices for card in self.profile.cards):
            self.profile.disable(time.strftime(f"Turned off after a {what} at %H:%M. Save it again "
                                               "once the settings pass a stability test."))
            log("boot profile turned off")
        if self.pending:
            self.pending = None
            self.revert_timer.stop()
        for card, original in self.baseline.items():
            try:
                self.devices[card].restore(original.snap)
                log(f"{card} clocks, voltage and power restored after the fault")
            except TuningError as e:
                log(f"{card} restore after the fault failed: {e}")

    # ── change pipeline: authorize, snapshot, apply, start the confirmation countdown ──
    def _change(self, msg: QDBusMessage, action: str, card: str, description: str, apply) -> None:
        msg.setDelayedReply(True)
        sender = msg.service()

        def authorized(allowed: bool, reason: str):
            if not allowed:
                self._reply(msg, {"ok": False, "error": reason})
                return
            if card not in (self.controls if action.startswith("gpu") else self.devices):
                self._reply(msg, {"ok": False, "error": f"unknown device {card!r}"})
                return
            before = self._state(card)
            try:
                apply(self.devices[card])
            except (TuningError, ValueError) as e:
                try:
                    self._restore(card, before)
                except TuningError:
                    pass
                self._reply(msg, {"ok": False, "error": str(e)})
                return
            if card not in self.baseline:
                self.baseline[card] = before
                self._save_baseline()
            if self.pending is None:
                self.pending = {"owner": sender, "items": [], "undo": {}}
            self.pending["undo"].setdefault(card, before)
            self.pending["items"].append(f"{card}: {description}")
            self.pending["owner"] = sender
            self.pending["deadline"] = time.monotonic() + CONFIRM_SECONDS
            self.revert_timer.start(CONFIRM_SECONDS * 1000)
            pid, uid = self.auth.caller(sender)
            log(f"{card}: {description} (uid {uid}, pid {pid}); waiting for confirmation")
            self._reply(msg, {"ok": True, "pending": self._pending_json(sender)})

        self.auth.check(sender, action, authorized)

    # ── D-Bus API ──
    @Slot(result=str)
    def Version(self) -> str:
        return __version__

    @Slot(result=str)
    def Probe(self) -> str:
        """Capability report as JSON (see probe.py)."""
        return json.dumps(probe())

    @Slot(QDBusMessage, result=str)
    def GetState(self, msg: QDBusMessage) -> str:
        cards = {}
        for card, c in self.controls.items():
            profiles, active = c.profiles()
            curve = self.fans.get(card)
            edge, junction = c.temps()
            od = c.overdrive()
            if od:
                od["voltage_range"] = list(VOLTAGE_OFFSET_RANGE)
                od["boot"] = self.boot[card].get("od")
            cards[card] = {
                "power": c.power(), "level": c.level(), "overdrive": od,
                "profiles": [[i, n] for i, n in profiles if n != "CUSTOM"], "profile": active,
                "fan": {"mode": "curve" if curve else _FAN_MODE_NAMES.get(c.fan_mode(), "unknown"),
                        "curve": [list(p) for p in curve.points] if curve else None,
                        "percent": c.fan_percent()},
                "temp": edge, "junction": junction, "changed": card in self.baseline,
                "risky": self._risky(card),
                "is_boot_profile": self.profile.cards.get(card) == self._state(card).to_json(),
            }
        return json.dumps({"cards": cards, "cpu": self._cpu_state(), "pending": self._pending_json(msg.service()),
                           "confirm_seconds": CONFIRM_SECONDS,
                           "faults": self.faults, "fault_count": self.fault_count,
                           "fault_watch": self.watcher.available,
                           "boot_profile": self.profile.to_json()})

    def _cpu_state(self) -> dict | None:
        if not self.cpu:
            return None
        table = self.cpu.smu.pm_table() or {}
        return {"table": table, "limits": {"ppt": table.get("ppt_limit"), "tdc": table.get("tdc_limit"),
                                           "edc": table.get("edc_limit")},
                "ranges": self.cpu.limit_ranges(), "boot": self.boot["cpu"], "co": self.cpu.curve(),
                "co_readable": self.cpu.co_readable, "co_error": self.cpu.co_error,
                "co_range": list(CO_RANGE), "per_core": self.cpu.smu.per_core_co_supported(),
                "ccds": self.cpu.smu.ccds, "changed": "cpu" in self.baseline, "risky": self._risky("cpu"),
                "is_boot_profile": self.profile.cards.get("cpu") == self._state("cpu").to_json()}

    @Slot(str, QDBusMessage, result=str)
    def SetCpuLimits(self, values_json: str, msg: QDBusMessage) -> str:
        """values_json: any of {"ppt": W, "tdc": A, "edc": A}."""
        try:
            values = {k: float(v) for k, v in json.loads(values_json).items() if k in ("ppt", "tdc", "edc")}
        except (ValueError, TypeError, AttributeError):
            msg.setDelayedReply(True)
            self._reply(msg, {"ok": False, "error": "invalid limits request"})
            return ""
        units = {"ppt": "W", "tdc": "A", "edc": "A"}
        description = ", ".join(f"{k.upper()} {v:.0f} {units[k]}" for k, v in values.items()) or "no change"
        self._change(msg, "cpu-limits", "cpu", description, lambda c: c.set_limits(**values))
        return ""

    @Slot(str, QDBusMessage, result=str)
    def SetCurveOptimizer(self, margins_json: str, msg: QDBusMessage) -> str:
        """margins_json: one margin per core, in core order."""
        try:
            margins = [int(m) for m in json.loads(margins_json)]
        except (ValueError, TypeError):
            msg.setDelayedReply(True)
            self._reply(msg, {"ok": False, "error": "invalid Curve Optimizer request"})
            return ""
        description = ("Curve Optimizer all cores " + str(margins[0]) if len(set(margins)) == 1
                       else "Curve Optimizer " + " ".join(str(m) for m in margins))
        self._change(msg, "cpu-curve", "cpu", description, lambda c: c.set_curve(margins))
        return ""

    @Slot(str, float, QDBusMessage, result=str)
    def SetPowerLimit(self, card: str, watts: float, msg: QDBusMessage) -> str:
        self._change(msg, "gpu-power", card, f"power limit {watts:.0f} W",
                     lambda c: c.set_power(watts))
        return ""

    @Slot(str, str, int, QDBusMessage, result=str)
    def SetPerformance(self, card: str, level: str, profile: int, msg: QDBusMessage) -> str:
        """level "" keeps the current one; profile -1 keeps the current one."""
        def apply(c: AmdGpuControl):
            if level:
                c.set_level(level)
            if profile >= 0:
                c.set_profile(profile)
        names = dict(self.controls[card].profiles()[0]) if card in self.controls else {}
        parts = ([f"level {level}"] if level else []) + ([f"profile {names.get(profile, profile)}"]
                                                          if profile >= 0 else [])
        self._change(msg, "gpu-profile", card, ", ".join(parts) or "performance unchanged", apply)
        return ""

    @Slot(str, str, QDBusMessage, result=str)
    def SetOverdrive(self, card: str, values_json: str, msg: QDBusMessage) -> str:
        """values_json: any of {"sclk_max": MHz, "mclk_max": MHz, "voltage_offset": mV}."""
        try:
            values = {k: int(v) for k, v in json.loads(values_json).items()
                      if k in ("sclk_max", "mclk_max", "voltage_offset")}
        except (ValueError, TypeError, AttributeError):
            msg.setDelayedReply(True)
            self._reply(msg, {"ok": False, "error": "invalid overdrive request"})
            return ""
        names = {"sclk_max": ("core clock", "MHz"), "mclk_max": ("memory clock", "MHz"),
                 "voltage_offset": ("voltage offset", "mV")}
        description = ", ".join(f"{names[k][0]} {v} {names[k][1]}" for k, v in values.items()) or "no change"
        self._change(msg, "gpu-clocks", card, description, lambda c: c.set_overdrive(**values))
        return ""

    @Slot(str, str, QDBusMessage, result=str)
    def SetFanCurve(self, card: str, curve_json: str, msg: QDBusMessage) -> str:
        """curve_json: [[temp °C, fan %], ...], or "" to hand the fan back to firmware."""
        try:
            points = json.loads(curve_json) if curve_json else None
            if points is not None:
                FanCurve(points)  # validate before asking for a password
        except ValueError as e:
            msg.setDelayedReply(True)
            self._reply(msg, {"ok": False, "error": str(e)})
            return ""
        description = "fan curve " + " ".join(f"{t:.0f}°C→{p:.0f}%" for t, p in points) if points \
            else "fan on firmware control"
        self._change(msg, "gpu-fan", card, description, lambda c: self._set_fan(card, points))
        return ""

    def _authorized(self, msg: QDBusMessage, action: str, run) -> None:
        """Delayed reply with run()'s result once polkit allows the caller."""
        msg.setDelayedReply(True)

        def done(allowed: bool, reason: str):
            self._reply(msg, run() if allowed else {"ok": False, "error": reason})
        self.auth.check(msg.service(), action, done)

    @Slot(str, QDBusMessage, result=str)
    def SaveBootProfile(self, card: str, msg: QDBusMessage) -> str:
        """Applies the card's current settings at every boot from now on."""
        def run():
            if card not in self.devices:
                return {"ok": False, "error": f"unknown device {card!r}"}
            if self.pending:
                return {"ok": False, "error": "keep or revert the current change first"}
            self.profile.store(card, self._state(card).to_json())
            self.profile.mark_applied()  # these settings are live now, so this session counts
            pid, uid = self.auth.caller(msg.service())
            log(f"{card} boot profile saved (uid {uid}, pid {pid})")
            return {"ok": True}
        self._authorized(msg, "boot-profile", run)
        return ""

    @Slot(QDBusMessage, result=str)
    def EnableBootProfile(self, msg: QDBusMessage) -> str:
        """Turns a profile that was switched off (after a crash or GPU hang) back on."""
        def run():
            if not self.profile.cards:
                return {"ok": False, "error": "no boot profile saved"}
            self.profile.enable()
            log("boot profile re-enabled")
            return {"ok": True}
        self._authorized(msg, "boot-profile", run)
        return ""

    @Slot(str, QDBusMessage, result=str)
    def ClearBootProfile(self, card: str, msg: QDBusMessage) -> str:
        """Stops applying settings at boot. Needs no authorization: it only makes boot safer."""
        self.profile.remove(card)
        log(f"{card} boot profile removed")
        return json.dumps({"ok": True})

    @Slot(QDBusMessage, result=str)
    def Confirm(self, msg: QDBusMessage) -> str:
        if not self.pending:
            return json.dumps({"ok": False, "error": "nothing to confirm"})
        if self.pending["owner"] != msg.service():
            return json.dumps({"ok": False, "error": "the change was made by another client"})
        log("confirmed " + "; ".join(self.pending["items"]))
        self.pending = None
        self.revert_timer.stop()
        return json.dumps({"ok": True})

    @Slot(QDBusMessage, result=str)
    def Revert(self, msg: QDBusMessage) -> str:
        """Undo the unconfirmed change now. Anyone may do this: it only goes back to the previous values."""
        if not self.pending:
            return json.dumps({"ok": False, "error": "nothing to revert"})
        log("reverting on request: " + "; ".join(self.pending["items"]))
        error = self._revert_pending()
        return json.dumps({"ok": error is None, "error": error})

    @Slot(str, QDBusMessage, result=str)
    def Reset(self, card: str, msg: QDBusMessage) -> str:
        """Back to the card's settings from before Rankine changed them. Needs no authorization."""
        state = self.baseline.get(card)
        if state is None:
            return json.dumps({"ok": True})
        if self.pending:
            self.pending["undo"].pop(card, None)
            if not self.pending["undo"]:
                self.pending = None
                self.revert_timer.stop()
        try:
            self._restore(card, state)
        except TuningError as e:
            return json.dumps({"ok": False, "error": str(e)})
        del self.baseline[card]
        self._save_baseline()
        log(f"{card} reset to its original settings")
        return json.dumps({"ok": True})


def reset_from_baseline(runtime_dir: str, controls: dict | None = None) -> int:
    """Crash recovery: restore whatever a previous run left changed. Safe to run when nothing was."""
    path = os.path.join(runtime_dir, "baseline.json")
    try:
        with open(path) as f:
            baseline = json.load(f)
    except FileNotFoundError:
        return 0
    except (OSError, ValueError) as e:
        log(f"cannot read {path}: {e}")
        return 1
    devices, status = dict(amd_controls() if controls is None else controls), 0
    if "cpu" in baseline and "cpu" not in devices:
        cpu = ryzen_control()
        if cpu:
            devices["cpu"] = cpu
    for card, data in baseline.items():
        state = CardState.from_json(data)
        control = devices.get(card)
        if control is None:
            continue
        try:
            control.restore(state.snap)
            if card != "cpu":
                control.set_fan_auto()
            log(f"{card} restored to its original settings")
        except TuningError as e:
            log(f"{card} restore failed: {e}")
            status = 1
    os.remove(path)
    return status


def cpu_report(verify_co: bool = False) -> int:
    """Read-only check of the Ryzen SMU interface, for verifying a new CPU or table version."""
    smu = RyzenSmu()
    if not smu.available:
        print("ryzen_smu is not loaded")
        return 1
    version = smu.table_version()
    report = {"driver": smu.driver_version(), "codename": smu.codename(),
              "pm_table_version": hex(version) if version is not None else None,
              "layout_known": version in LAYOUTS, "ccds": smu.ccds,
              "per_core_co_supported": smu.per_core_co_supported()}
    try:
        table = smu.pm_table()
        report["pm_table"] = table
        if table is None and version in LAYOUTS:
            report["pm_table_error"] = "values failed the sanity check"
    except OSError as e:
        report["pm_table_error"] = str(e)
    try:
        report["curve_optimizer"] = [smu.get_co(c) for c in smu.all_cores]
    except TuningError as e:
        report["curve_optimizer_error"] = str(e)
    if verify_co and "curve_optimizer" in report:
        # A read of 0 is also what a command that does nothing returns: write a small margin to the
        # last core, read it back, then put the original value back.
        core = smu.all_cores[-1]
        original = report["curve_optimizer"][-1]
        probe_margin = -5 if original != -5 else -4
        try:
            smu.set_co(core, probe_margin)
            read_back = smu.get_co(core)
        finally:
            smu.command("mp1", MP1_SET_CO, [smu.core_mask(core) | (original & 0xFFFF)])
        report["curve_optimizer_verify"] = {"core": core, "wrote": probe_margin, "read_back": read_back,
                                            "restored": smu.get_co(core) == original,
                                            "ok": read_back == probe_margin}
    print(json.dumps(report, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rankine-tuned", description="Rankine tuning helper service.")
    parser.add_argument("--session", action="store_true",
                        help="serve on the session bus, unprivileged and without polkit (development)")
    parser.add_argument("--reset", action="store_true",
                        help="restore settings a crashed run left changed, then exit")
    parser.add_argument("--cpu-report", action="store_true",
                        help="print what ryzen_smu reports (PM table, Curve Optimizer), read-only, then exit")
    parser.add_argument("--verify-co", action="store_true",
                        help="with --cpu-report: write -5 to the last core's Curve Optimizer, read it "
                             "back and restore it, to prove the read command works")
    parser.add_argument("--version", action="version", version=f"rankine-tuned {__version__}")
    args = parser.parse_args(argv)
    if args.cpu_report:
        return cpu_report(args.verify_co)

    runtime_dir = (os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "rankine-tuned")
                   if args.session else SYSTEM_RUNTIME_DIR)
    state_dir = (os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
                              "rankine-tuned") if args.session else SYSTEM_STATE_DIR)
    if args.reset:
        return reset_from_baseline(runtime_dir)

    app = QCoreApplication(sys.argv[:1])
    bus = QDBusConnection.sessionBus() if args.session else QDBusConnection.systemBus()
    if not bus.isConnected():
        log(f"cannot connect to the D-Bus: {bus.lastError().message()}")
        return 1
    if not args.session and os.geteuid() != 0:
        log("the system service must run as root (use --session to develop)")
        return 1

    reset_from_baseline(runtime_dir)  # a previous run may have died without restoring
    service = Tuned(bus, Authorizer(bus, enforce=not args.session), runtime_dir, state_dir=state_dir)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Python only runs signal handlers between bytecodes; wake the interpreter so SIGTERM is not stuck.
    wake = QTimer(interval=500)
    wake.timeout.connect(lambda: None)
    wake.start()
    app.aboutToQuit.connect(service.restore_all)
    app.aboutToQuit.connect(service.profile.end_session)  # only reached on a clean stop
    bus.registerObject(OBJECT_PATH, service, QDBusConnection.ExportAllSlots)
    if not bus.registerService(BUS_NAME):
        log(f"cannot own {BUS_NAME}: {bus.lastError().message()}")
        return 1
    log(f"{__version__} serving {BUS_NAME}")
    return app.exec()
