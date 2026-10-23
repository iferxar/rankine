"""rankine-tuned: the system service that applies GPU tuning on behalf of the UI.

Safety rules (docs/TUNING.md):
- every change must be confirmed within CONFIRM_SECONDS or it is reverted, by this service, not the UI;
- what the card looked like before Rankine touched it is kept in a baseline file and restored when
  the service stops, or by `rankine-tuned --reset` (ExecStopPost) if it crashed;
- nothing is applied at boot.
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
from .fan import FanCurve
from .gpu import FAN_AUTO, AmdGpuControl, TuningError, amd_controls
from .polkit import Authorizer
from .probe import probe

CONFIRM_SECONDS = 15
FAN_INTERVAL_MS = 1000
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
                 controls: dict[str, AmdGpuControl] | None = None):
        super().__init__()
        self.bus = bus
        self.auth = authorizer
        self.baseline_path = os.path.join(runtime_dir, "baseline.json")
        os.makedirs(runtime_dir, exist_ok=True)
        self.controls = amd_controls() if controls is None else controls
        self.fans: dict[str, FanCurve] = {}
        self.baseline: dict[str, CardState] = {}
        self.pending: dict | None = None  # {"owner", "items", "deadline", "undo": {card: CardState}}
        self.revert_timer = QTimer(self, singleShot=True)
        self.revert_timer.timeout.connect(self._expire)
        self.fan_timer = QTimer(self, interval=FAN_INTERVAL_MS)
        self.fan_timer.timeout.connect(self._drive_fans)

    # ── state helpers ──
    def _state(self, card: str) -> CardState:
        curve = self.fans.get(card)
        return CardState(self.controls[card].snapshot(), [list(p) for p in curve.points] if curve else None)

    def _restore(self, card: str, state: CardState) -> None:
        control = self.controls[card]
        try:
            control.restore(state.snap)
        finally:
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

    # ── change pipeline: authorize, snapshot, apply, start the confirmation countdown ──
    def _change(self, msg: QDBusMessage, action: str, card: str, description: str, apply) -> None:
        msg.setDelayedReply(True)
        sender = msg.service()

        def authorized(allowed: bool, reason: str):
            if not allowed:
                self._reply(msg, {"ok": False, "error": reason})
                return
            if card not in self.controls:
                self._reply(msg, {"ok": False, "error": f"unknown card {card!r}"})
                return
            before = self._state(card)
            try:
                apply(self.controls[card])
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
            cards[card] = {
                "power": c.power(), "level": c.level(),
                "profiles": [[i, n] for i, n in profiles if n != "CUSTOM"], "profile": active,
                "fan": {"mode": "curve" if curve else _FAN_MODE_NAMES.get(c.fan_mode(), "unknown"),
                        "curve": [list(p) for p in curve.points] if curve else None,
                        "percent": c.fan_percent()},
                "temp": edge, "junction": junction, "changed": card in self.baseline,
            }
        return json.dumps({"cards": cards, "pending": self._pending_json(msg.service()),
                           "confirm_seconds": CONFIRM_SECONDS})

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


def reset_from_baseline(runtime_dir: str) -> int:
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
    controls, status = amd_controls(), 0
    for card, data in baseline.items():
        state = CardState.from_json(data)
        control = controls.get(card)
        if control is None:
            continue
        try:
            control.restore(state.snap)
            control.set_fan_auto()
            log(f"{card} restored to its original settings")
        except TuningError as e:
            log(f"{card} restore failed: {e}")
            status = 1
    os.remove(path)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rankine-tuned", description="Rankine tuning helper service.")
    parser.add_argument("--session", action="store_true",
                        help="serve on the session bus, unprivileged and without polkit (development)")
    parser.add_argument("--reset", action="store_true",
                        help="restore settings a crashed run left changed, then exit")
    parser.add_argument("--version", action="version", version=f"rankine-tuned {__version__}")
    args = parser.parse_args(argv)

    runtime_dir = (os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "rankine-tuned")
                   if args.session else SYSTEM_RUNTIME_DIR)
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
    service = Tuned(bus, Authorizer(bus, enforce=not args.session), runtime_dir)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Python only runs signal handlers between bytecodes; wake the interpreter so SIGTERM is not stuck.
    wake = QTimer(interval=500)
    wake.timeout.connect(lambda: None)
    wake.start()
    app.aboutToQuit.connect(service.restore_all)
    bus.registerObject(OBJECT_PATH, service, QDBusConnection.ExportAllSlots)
    if not bus.registerService(BUS_NAME):
        log(f"cannot own {BUS_NAME}: {bus.lastError().message()}")
        return 1
    log(f"{__version__} serving {BUS_NAME}")
    return app.exec()
