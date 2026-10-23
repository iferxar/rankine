"""Watches the kernel log for amdgpu hangs and resets, the sign that a clock or voltage setting is unstable."""
from __future__ import annotations

import errno
import os
import re
import time
from typing import Callable

from PySide6.QtCore import QObject, QSocketNotifier

KMSG = "/dev/kmsg"
PATTERN = re.compile(r"amdgpu.*(ring \S+ timeout|GPU reset begin|GPU recovery|gpu hang)", re.I)
GROUP_SECONDS = 30  # one hang logs many lines; count them as one fault


class FaultWatcher(QObject):
    def __init__(self, on_fault: Callable[[str], None], path: str = KMSG):
        super().__init__()
        self.on_fault = on_fault
        self.available = False
        self.error = ""
        self._last = 0.0
        self._buffer = b""
        try:
            self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            self.fd = None
            self.error = f"cannot read the kernel log: {e.strerror}"
            return
        try:
            os.lseek(self.fd, 0, os.SEEK_END)  # only new messages
        except OSError:
            pass  # pipes (tests) cannot seek
        self.notifier = QSocketNotifier(self.fd, QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._read)
        self.available = True

    def _read(self):
        while True:
            try:
                chunk = os.read(self.fd, 8192)
            except OSError as e:
                if e.errno == errno.EPIPE:  # /dev/kmsg: we fell behind and records were overwritten
                    continue
                if e.errno != errno.EAGAIN:
                    self.error = f"kernel log read failed: {e.strerror}"
                break
            if not chunk:  # end of file: only pipes do this (tests); stop listening
                self.notifier.setEnabled(False)
                break
            self._buffer += chunk
            # /dev/kmsg returns one newline-terminated record per read; a pipe may return several.
            *lines, self._buffer = self._buffer.split(b"\n")
            for raw in lines:
                text = raw.decode(errors="replace").split(";", 1)[-1].strip()
                self._check(text)

    def _check(self, text: str):
        if PATTERN.search(text) and time.monotonic() - self._last > GROUP_SECONDS:
            self._last = time.monotonic()
            self.on_fault(text)
