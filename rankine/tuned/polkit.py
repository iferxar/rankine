"""Asks polkit whether the D-Bus caller may perform an action, without blocking the service."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QProcess
from PySide6.QtDBus import QDBusConnection

ACTION_PREFIX = "io.github.iferxar.Rankine.Tuned."


def _start_time(pid: int) -> int | None:
    """Process start time in clock ticks, which pins the pid against reuse (field 22 of /proc/pid/stat)."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            return int(f.read().rsplit(")", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        return None


class Authorizer(QObject):
    def __init__(self, bus: QDBusConnection, enforce: bool):
        super().__init__()
        self.bus = bus
        self.enforce = enforce  # off only for the unprivileged development helper on the session bus
        self._running: set[QProcess] = set()

    def caller(self, sender: str) -> tuple[int | None, int | None]:
        iface = self.bus.interface()
        pid, uid = iface.servicePid(sender), iface.serviceUid(sender)
        return (pid.value() if pid.isValid() else None, uid.value() if uid.isValid() else None)

    def check(self, sender: str, action: str, done: Callable[[bool, str], None]) -> None:
        """Calls done(allowed, reason). May show the user an authentication dialog."""
        if not self.enforce:
            done(True, "")
            return
        pid, uid = self.caller(sender)
        start = _start_time(pid) if pid else None
        if pid is None or uid is None or start is None:
            done(False, "cannot identify the calling process")
            return
        proc = QProcess(self)
        self._running.add(proc)

        def finish(allowed: bool, reason: str):
            if proc not in self._running:
                return
            self._running.discard(proc)
            proc.deleteLater()
            done(allowed, reason)

        # pkcheck exit codes: 0 authorized, 1 not authorized, 2 no authentication agent, 3 dismissed.
        reasons = {1: "not authorized", 2: "no polkit authentication agent is running in your session",
                   3: "authentication was dismissed"}
        proc.finished.connect(lambda code, _s: finish(code == 0, reasons.get(code, f"pkcheck exit code {code}")))
        proc.errorOccurred.connect(lambda e: e == QProcess.ProcessError.FailedToStart
                                   and finish(False, "pkcheck is not installed"))
        proc.start("pkcheck", ["--action-id", ACTION_PREFIX + action,
                               "--process", f"{pid},{start},{uid}", "--allow-user-interaction"])
