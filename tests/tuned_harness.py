"""Runs rankine-tuned on the session bus against a fake GPU (used by test_tuned.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection

from rankine.tuned import service
from rankine.tuned.bus import BUS_NAME, OBJECT_PATH
from rankine.tuned.polkit import Authorizer
from tests.fakegpu import fake_control

root, runtime, seconds = sys.argv[1], sys.argv[2], float(sys.argv[3])
card = sys.argv[4] if len(sys.argv) > 4 else "card9"
kmsg = sys.argv[5] if len(sys.argv) > 5 else ""
service.CONFIRM_SECONDS = seconds
app = QCoreApplication(sys.argv[:1])
bus = QDBusConnection.sessionBus()
control = fake_control(card, os.path.join(root, "device"), os.path.join(root, "device/hwmon/hwmon9"))
tuned = service.Tuned(bus, Authorizer(bus, enforce=False), runtime, {card: control}, kmsg)
app.aboutToQuit.connect(tuned.restore_all)
import signal
signal.signal(signal.SIGTERM, lambda *_: app.quit())
from PySide6.QtCore import QTimer
wake = QTimer(interval=100); wake.timeout.connect(lambda: None); wake.start()
bus.registerObject(OBJECT_PATH, tuned, QDBusConnection.ExportAllSlots)
if not bus.registerService(BUS_NAME):
    sys.exit("bus name taken")
print("ready", flush=True)
app.exec()
