"""rankine-tuned: the system service that will apply tuning. For now it only answers capability probes."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys

from PySide6.QtCore import ClassInfo, QCoreApplication, QObject, Slot
from PySide6.QtDBus import QDBusConnection

from .. import __version__
from .bus import BUS_NAME, INTERFACE, OBJECT_PATH
from .probe import probe


@ClassInfo({"D-Bus Interface": INTERFACE})
class Tuned(QObject):
    @Slot(result=str)
    def Version(self) -> str:
        return __version__

    @Slot(result=str)
    def Probe(self) -> str:
        """Capability report as JSON (see probe.py)."""
        return json.dumps(probe())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rankine-tuned", description="Rankine tuning helper service.")
    parser.add_argument("--session", action="store_true",
                        help="serve on the session bus, unprivileged (development)")
    parser.add_argument("--version", action="version", version=f"rankine-tuned {__version__}")
    args = parser.parse_args(argv)

    app = QCoreApplication(sys.argv[:1])
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    bus = QDBusConnection.sessionBus() if args.session else QDBusConnection.systemBus()
    if not bus.isConnected():
        print(f"rankine-tuned: cannot connect to the D-Bus: {bus.lastError().message()}", file=sys.stderr)
        return 1
    if not args.session and os.geteuid() != 0:
        print("rankine-tuned: the system service must run as root (use --session to develop)",
              file=sys.stderr)
        return 1

    service = Tuned()
    bus.registerObject(OBJECT_PATH, service, QDBusConnection.ExportAllSlots)
    if not bus.registerService(BUS_NAME):
        print(f"rankine-tuned: cannot own {BUS_NAME}: {bus.lastError().message()}", file=sys.stderr)
        return 1
    print(f"rankine-tuned {__version__} serving {BUS_NAME}", file=sys.stderr, flush=True)
    return app.exec()
