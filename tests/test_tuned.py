import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rankine.tuned.bus import BUS_NAME, INTERFACE, OBJECT_PATH
from rankine.tuned.fan import FanCurve, validate
from rankine.tuned.gpu import AmdGpuControl, TuningError
from tests import fakegpu


class FanCurveTest(unittest.TestCase):
    def test_interpolates_and_clamps(self):
        c = FanCurve([[40, 20], [80, 60]])
        self.assertEqual(c.target(30), 20)
        c.current = None
        self.assertAlmostEqual(c.target(60), 40)
        self.assertEqual(c.target(95), 60)

    def test_hysteresis_slows_down_late(self):
        c = FanCurve([[40, 20], [80, 60]])
        c.target(70)                          # 50 %
        self.assertAlmostEqual(c.target(68), 50)   # within 3 °C: hold
        self.assertAlmostEqual(c.target(60), 43)   # follows temp + 3 °C

    def test_panic_on_hot_junction(self):
        self.assertEqual(FanCurve([[40, 20], [80, 60]]).target(70, junction=101), 100)

    def test_rejects_bad_curves(self):
        for bad in ([[40, 20]], [[40, 50], [60, 30]], [[60, 20], [40, 30]], [[40, 20], [60, 130]], "x"):
            with self.assertRaises(ValueError):
                validate(bad)


class GpuControlTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.dev, self.hwmon = fakegpu.make(self.root)
        self.c = AmdGpuControl("card9", self.dev, self.hwmon)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_power_range_is_enforced(self):
        self.c.set_power(245)
        self.assertEqual(fakegpu.read(f"{self.hwmon}/power1_cap"), "245000000")
        with self.assertRaises(TuningError):
            self.c.set_power(300)

    def test_profiles_exclude_custom_writes(self):
        self.c.set_profile(1)
        self.assertEqual(fakegpu.read(f"{self.dev}/pp_power_profile_mode"), "1")
        with self.assertRaises(TuningError):
            self.c.set_profile(6)

    def test_fan_percent_switches_to_manual(self):
        self.c.set_fan_percent(50)
        self.assertEqual(fakegpu.read(f"{self.hwmon}/pwm1_enable"), "1")
        self.assertEqual(fakegpu.read(f"{self.hwmon}/pwm1"), "128")

    def test_snapshot_restore(self):
        snap = self.c.snapshot()
        self.c.set_power(240)
        self.c.set_level("high")
        self.c.restore(snap)
        self.assertEqual(fakegpu.read(f"{self.hwmon}/power1_cap"), "264000000")
        self.assertEqual(fakegpu.read(f"{self.dev}/power_dpm_force_performance_level"), "auto")


@unittest.skipUnless(shutil.which("busctl") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"), "needs a session bus")
class ServiceTest(unittest.TestCase):
    CONFIRM = 1.5

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.runtime = os.path.join(self.root, "run")
        self.dev, self.hwmon = fakegpu.make(self.root)
        harness = os.path.join(os.path.dirname(__file__), "tuned_harness.py")
        self.proc = subprocess.Popen([sys.executable, harness, self.root, self.runtime, str(self.CONFIRM)],
                                     stdout=subprocess.PIPE, text=True)
        self.assertEqual(self.proc.stdout.readline().strip(), "ready")

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait(5)
        self.proc.stdout.close()
        shutil.rmtree(self.root)

    def call(self, method, signature="", *args):
        out = subprocess.run(["busctl", "--user", "--json=short", "call", BUS_NAME, OBJECT_PATH, INTERFACE,
                              method, signature, *map(str, args)],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(json.loads(out)["data"][0])

    def cap(self):
        return fakegpu.read(f"{self.hwmon}/power1_cap")

    def test_unconfirmed_change_reverts(self):
        r = self.call("SetPowerLimit", "sd", "card9", 240)
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.cap(), "240000000")
        self.assertEqual(self.call("GetState")["pending"]["items"], ["card9: power limit 240 W"])
        time.sleep(self.CONFIRM + 0.7)
        self.assertEqual(self.cap(), "264000000")
        self.assertIsNone(self.call("GetState")["pending"])

    def test_bad_request_is_refused(self):
        r = self.call("SetPowerLimit", "sd", "card9", 500)
        self.assertFalse(r["ok"])
        self.assertIn("between 237 and 264", r["error"])
        self.assertEqual(self.cap(), "264000000")

    def test_revert_and_reset(self):
        self.call("SetPerformance", "ssi", "card9", "high", 2)
        self.assertEqual(self.call("Revert")["ok"], True)
        self.assertEqual(fakegpu.read(f"{self.dev}/power_dpm_force_performance_level"), "auto")
        self.call("SetPowerLimit", "sd", "card9", 250)
        # Confirm must come from the caller that made the change; busctl uses a new connection each time.
        self.assertFalse(self.call("Confirm")["ok"])
        self.assertTrue(self.call("Reset", "s", "card9")["ok"])
        self.assertEqual(self.cap(), "264000000")
        self.assertIsNone(self.call("GetState")["pending"])

    def test_fan_curve_runs_and_stops_on_shutdown(self):
        r = self.call("SetFanCurve", "ss", "card9", "[[40, 20], [80, 60]]")
        self.assertTrue(r["ok"], r)
        self.assertEqual(fakegpu.read(f"{self.hwmon}/pwm1_enable"), "1")
        self.assertEqual(fakegpu.read(f"{self.hwmon}/pwm1"), str(round(30 * 255 / 100)))  # 50 °C edge
        fakegpu.write(f"{self.hwmon}/temp1_input", 70000)
        time.sleep(1.3)
        self.assertEqual(fakegpu.read(f"{self.hwmon}/pwm1"), str(round(50 * 255 / 100)))
        self.assertTrue(os.path.exists(os.path.join(self.runtime, "baseline.json")))
        self.proc.terminate()
        self.proc.wait(5)
        self.assertEqual(fakegpu.read(f"{self.hwmon}/pwm1_enable"), "2")
        self.assertFalse(os.path.exists(os.path.join(self.runtime, "baseline.json")))

    def test_invalid_curve_is_refused(self):
        r = self.call("SetFanCurve", "ss", "card9", "[[40, 60], [80, 20]]")
        self.assertFalse(r["ok"])
        self.assertEqual(fakegpu.read(f"{self.hwmon}/pwm1_enable"), "2")


if __name__ == "__main__":
    unittest.main()
