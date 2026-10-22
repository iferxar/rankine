"""Qt front end: exposes the latest snapshot to QML and refreshes it on a timer."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .sensors.monitor import BaseMonitor

QML_DIR = Path(__file__).parent / "qml"
ICON = Path(__file__).parent / "icons" / "rankine.svg"


class Backend(QObject):
    dataChanged = Signal()

    def __init__(self, monitor: BaseMonitor, interval: float):
        super().__init__()
        self._monitor = monitor
        self._data = monitor.sample()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(int(interval * 1000))

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
