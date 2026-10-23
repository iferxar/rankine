"""UI side of tuning: talks to rankine-tuned over D-Bus without blocking the window."""
from __future__ import annotations

import json
import os
from statistics import fmean

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher

from .tuned import bus as tuned_bus
from .tuned.probe import probe

CALL_TIMEOUT_MS = 120_000  # long enough for the user to type a password in the polkit dialog
COMPARE_SAMPLES = 20       # seconds of readings before and after a change
COMPARE_KEYS = ("gpu.power", "gpu.temp", "gpu.hotspot", "gpu.mhz", "gpu.fan_rpm", "gpu.load")


class TuningClient(QObject):
    reportChanged = Signal()
    stateChanged = Signal()
    busyChanged = Signal()
    messageChanged = Signal()
    comparisonChanged = Signal()

    def __init__(self, backend):
        super().__init__()
        self._backend = backend
        self._session = tuned_bus.use_session_bus()
        # One connection for every call: Confirm is only accepted from the caller that made the change.
        self._bus = QDBusConnection.sessionBus() if self._session else QDBusConnection.systemBus()
        self._report: dict = {}
        self._state: dict = {}
        self._busy = False
        self._message = ""
        self._comparison: dict = {}
        self._after: dict[str, list[float]] | None = None
        self._active = False
        self._polling = False
        self._watchers: set[QDBusPendingCallWatcher] = set()
        backend.dataChanged.connect(self._tick)

    # ── properties ──
    @Property("QVariantMap", notify=reportChanged)
    def report(self):
        return self._report

    @Property("QVariantMap", notify=stateChanged)
    def state(self):
        return self._state

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @Property(str, notify=messageChanged)
    def message(self):
        return self._message

    @Property("QVariantMap", notify=comparisonChanged)
    def comparison(self):
        return self._comparison

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.busyChanged.emit()

    def _set_message(self, text: str):
        self._message = text
        self.messageChanged.emit()

    @property
    def _helper_running(self) -> bool:
        return bool(self._report.get("helper", {}).get("running"))

    # ── D-Bus plumbing ──
    def _call(self, method: str, args: list, done, timeout: int = CALL_TIMEOUT_MS):
        msg = QDBusMessage.createMethodCall(tuned_bus.BUS_NAME, tuned_bus.OBJECT_PATH,
                                            tuned_bus.INTERFACE, method)
        msg.setArguments(args)
        watcher = QDBusPendingCallWatcher(self._bus.asyncCall(msg, timeout))
        self._watchers.add(watcher)

        def finished(w):
            self._watchers.discard(w)
            reply = w.reply()
            w.deleteLater()
            if reply.type() == QDBusMessage.MessageType.ReplyMessage:
                try:
                    done(json.loads(reply.arguments()[0]), None)
                except (ValueError, IndexError):
                    done(None, "unexpected reply from rankine-tuned")
            else:
                done(None, reply.errorMessage() or reply.errorName())

        watcher.finished.connect(finished)

    @Slot()
    def refresh(self):
        """Capability report from the helper, or from an in-process probe when it is not running."""
        def done(report, error):
            if report is None:
                report = probe()
                unit_installed = any(os.path.exists(f"{d}/{tuned_bus.UNIT}")
                                     for d in ("/usr/lib/systemd/system", "/etc/systemd/system"))
                report["helper"] = {"running": False, "installed": unit_installed, "error": error}
            else:
                report["helper"] = {"running": True, "bus": "session" if self._session else "system"}
            self._report = report
            self.reportChanged.emit()
            if self._helper_running:
                self._poll()
        self._call("Probe", [], done, timeout=3000)

    @Slot(bool)
    def setActive(self, active: bool):
        """The Tuning page is visible; poll live values while it is."""
        self._active = active
        if active:
            self.refresh()

    def _poll(self):
        if self._polling:
            return
        self._polling = True

        def done(state, error):
            self._polling = False
            if state is None:
                return
            self._state = state
            self.stateChanged.emit()
        self._call("GetState", [], done, timeout=3000)

    def _tick(self):
        if self._helper_running and (self._active or self._state.get("pending")):
            self._poll()
        if self._after is not None:
            snap = self._backend.data
            for key in COMPARE_KEYS:
                section, field = key.split(".")
                value = (snap.get(section) or {}).get(field)
                if isinstance(value, (int, float)):
                    self._after[key].append(value)
            collected = min(len(v) for v in self._after.values()) if self._after else 0
            self._comparison = {**self._comparison, "collected": collected,
                                "after": {k: fmean(v) for k, v in self._after.items() if v}}
            if collected >= COMPARE_SAMPLES:
                self._after = None
            self.comparisonChanged.emit()

    # ── changes ──
    def _change(self, method: str, args: list):
        if self._busy:
            return
        self._set_busy(True)
        self._set_message("")
        before = self._history_means()

        def done(result, error):
            self._set_busy(False)
            if result is None or not result.get("ok"):
                self._set_message((result or {}).get("error") or error or "failed")
                return
            pending = result.get("pending") or {}
            self._comparison = {"what": (pending.get("items") or [""])[-1], "before": before,
                                "after": {}, "collected": 0, "needed": COMPARE_SAMPLES}
            self._after = {k: [] for k in COMPARE_KEYS}
            self.comparisonChanged.emit()
            self._poll()
        self._call(method, args, done)

    def _history_means(self) -> dict:
        history = self._backend.data.get("history", {})
        return {k: fmean(history[k][-COMPARE_SAMPLES:]) for k in COMPARE_KEYS if history.get(k)}

    @Slot(str, float)
    def setPowerLimit(self, card: str, watts: float):
        self._change("SetPowerLimit", [card, float(watts)])

    @Slot(str, str, int)
    def setPerformance(self, card: str, level: str, profile: int):
        self._change("SetPerformance", [card, level, int(profile)])

    @Slot(str, "QVariantList")
    def setFanCurve(self, card: str, points):
        self._change("SetFanCurve", [card, json.dumps([[float(t), float(p)] for t, p in points])])

    @Slot(str)
    def setFanAuto(self, card: str):
        self._change("SetFanCurve", [card, ""])

    def _simple(self, method: str, args: list):
        def done(result, error):
            if result is None or not result.get("ok"):
                self._set_message((result or {}).get("error") or error or "failed")
            self._poll()
        self._call(method, args, done, timeout=5000)

    @Slot()
    def confirm(self):
        self._simple("Confirm", [])

    @Slot()
    def revert(self):
        self._simple("Revert", [])

    @Slot(str)
    def reset(self, card: str):
        self._simple("Reset", [card])

    @Slot()
    def clearComparison(self):
        self._comparison, self._after = {}, None
        self.comparisonChanged.emit()
