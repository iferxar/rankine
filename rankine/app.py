"""Qt front end: exposes the latest snapshot to QML and refreshes it on a timer."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Property, QObject, QProcess, QTimer, QUrl, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .sensors.monitor import BaseMonitor
from .tuned import bus as tuned_bus
from .tuned.probe import probe

QML_DIR = Path(__file__).parent / "qml"
ICON = Path(__file__).parent / "icons" / "rankine.svg"


class Backend(QObject):
    dataChanged = Signal()
    detectStateChanged = Signal()
    tuningChanged = Signal()

    def __init__(self, monitor: BaseMonitor, interval: float):
        super().__init__()
        self._monitor = monitor
        self._data = monitor.sample()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(int(interval * 1000))
        self._detect_proc: QProcess | None = None
        self._detect_state = ""
        self._tuning: dict = {}

    def _tick(self):
        self._data = self._monitor.sample()
        self.dataChanged.emit()

    @Property("QVariantMap", notify=dataChanged)
    def data(self):
        return self._data

    @Slot()
    def resetStats(self):
        self._monitor.reset_stats()
        self._tick()

    # DIMM configured speed/voltage live in SMBIOS tables, readable only by root:
    # run dmidecode once through polkit and cache the parsed result.
    @Property(str, notify=detectStateChanged)
    def detectState(self):
        return self._detect_state

    def _set_detect_state(self, state: str):
        self._detect_state = state
        self.detectStateChanged.emit()

    @Slot()
    def detectDimms(self):
        if self._detect_proc is not None:
            return
        dmidecode, pkexec = shutil.which("dmidecode"), shutil.which("pkexec")
        if not dmidecode or not pkexec:
            self._set_detect_state("needs dmidecode and polkit installed")
            return
        self._detect_proc = QProcess(self)
        self._detect_proc.finished.connect(self._on_detect_finished)
        self._detect_proc.start(pkexec, [dmidecode, "-t", "17"])
        self._set_detect_state("running")

    def _on_detect_finished(self, code: int, _status):
        proc, self._detect_proc = self._detect_proc, None
        output = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        error = bytes(proc.readAllStandardError()).decode(errors="replace").strip().splitlines()
        proc.deleteLater()
        if code == 0 and self._monitor.save_dimm_info(output):
            self._set_detect_state("")
            self._tick()
        elif code == 126:  # pkexec: authentication dialog dismissed
            self._set_detect_state("")
        else:
            self._set_detect_state(error[-1] if error else f"exit code {code}")

    # Tuning capabilities come from rankine-tuned when it runs; otherwise the same probe runs
    # in-process, so the page still explains what is available and how to set up the rest.
    @Property("QVariantMap", notify=tuningChanged)
    def tuning(self):
        return self._tuning

    @Slot()
    def refreshTuning(self):
        session = tuned_bus.use_session_bus()
        bus = QDBusConnection.sessionBus() if session else QDBusConnection.systemBus()
        iface = QDBusInterface(tuned_bus.BUS_NAME, tuned_bus.OBJECT_PATH, tuned_bus.INTERFACE, bus)
        iface.setTimeout(3000)
        reply = iface.call("Probe") if iface.isValid() else None
        if reply is not None and reply.type() == QDBusMessage.MessageType.ReplyMessage:
            report = json.loads(reply.arguments()[0])
            report["helper"] = {"running": True, "bus": "session" if session else "system"}
        else:
            report = probe()
            unit_installed = any(os.path.exists(f"{d}/{tuned_bus.UNIT}")
                                 for d in ("/usr/lib/systemd/system", "/etc/systemd/system"))
            report["helper"] = {"running": False, "installed": unit_installed,
                                "error": reply.errorMessage() if reply is not None
                                else iface.lastError().message()}
        self._tuning = report
        self.tuningChanged.emit()


def run(monitor: BaseMonitor, interval: float) -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QQuickStyle.setStyle(os.environ["QT_QUICK_CONTROLS_STYLE"])
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Rankine")
    app.setDesktopFileName("rankine")
    app.setWindowIcon(QIcon.fromTheme("rankine", QIcon(str(ICON))))

    backend = Backend(monitor, interval)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        return 1
    return app.exec()
