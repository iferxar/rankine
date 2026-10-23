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
from rankine.tuned.gpu import AmdGpuControl, TuningError, parse_overdrive
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


class OverdriveTest(unittest.TestCase):
    REAL = ("OD_SCLK:\n0: 500Mhz\n1: 2509Mhz\nOD_MCLK:\n0: 97Mhz\n1: 1000MHz\nOD_RANGE:\n"
            "SCLK:     500Mhz       3000Mhz\nMCLK:     674Mhz       1075Mhz\nOD_VDDGFX_OFFSET:\n0mV\n")

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.dev, self.hwmon = fakegpu.make(self.root)
        self.c = fakegpu.fake_control("card9", self.dev, self.hwmon)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_parses_rdna2_table(self):
        self.assertEqual(parse_overdrive(self.REAL), {
            "sclk": [500, 2509], "mclk": [97, 1000], "voltage_offset": 0,
            "range": {"sclk": [500, 3000], "mclk": [674, 1075]}})

    def test_commits_edits_together(self):
        self.c.set_overdrive(sclk_max=2400, voltage_offset=-50)
        od = self.c.overdrive()
        self.assertEqual((od["sclk"][1], od["mclk"][1], od["voltage_offset"]), (2400, 1000, -50))

    def test_rejects_out_of_range(self):
        for kwargs in ({"sclk_max": 3100}, {"sclk_max": 400}, {"mclk_max": 1100},
                       {"voltage_offset": -200}, {"voltage_offset": 10}):
            with self.assertRaises(TuningError, msg=kwargs):
                self.c.set_overdrive(**kwargs)
        self.assertEqual(self.c.overdrive()["sclk"][1], 2509)

    def test_restore_puts_overdrive_back(self):
        snap = self.c.snapshot()
        self.c.set_overdrive(sclk_max=2300, mclk_max=1050, voltage_offset=-75)
        self.c.restore(snap)
        self.assertEqual(self.c.snapshot(), snap)


@unittest.skipUnless(shutil.which("busctl") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"), "needs a session bus")
class ServiceTest(unittest.TestCase):
    CONFIRM = 1.5

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.runtime = os.path.join(self.root, "run")
        self.state = os.path.join(self.root, "state")
        self.dev, self.hwmon = fakegpu.make(self.root)
        self.kmsg = os.path.join(self.root, "kmsg")
        os.mkfifo(self.kmsg)
        self.start()

    def start(self):
        harness = os.path.join(os.path.dirname(__file__), "tuned_harness.py")
        self.proc = subprocess.Popen([sys.executable, harness, self.root, self.runtime, str(self.CONFIRM),
                                      "card9", self.kmsg, self.state, "fakecpu"],
                                     stdout=subprocess.PIPE, text=True)
        self.assertEqual(self.proc.stdout.readline().strip(), "ready")
        self.kernel = open(self.kmsg, "w")  # the harness opened the read end before printing "ready"

    def stop(self, crash=False):
        self.kernel.close()
        if crash:
            self.proc.kill()
        else:
            self.proc.terminate()
        self.proc.wait(5)
        self.proc.stdout.close()

    def tearDown(self):
        if self.proc.returncode is None:
            self.stop()
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
        state = self.call("GetState")
        self.assertIsNone(state["pending"])
        self.assertFalse(state["cards"]["card9"]["changed"])
        self.assertFalse(os.path.exists(os.path.join(self.runtime, "baseline.json")))

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
        self.stop()
        self.assertEqual(fakegpu.read(f"{self.hwmon}/pwm1_enable"), "2")
        self.assertFalse(os.path.exists(os.path.join(self.runtime, "baseline.json")))

    def od(self):
        od = parse_overdrive(fakegpu.read(f"{self.dev}/pp_od_clk_voltage"))
        return od["sclk"][1], od["voltage_offset"]

    def test_overdrive_reverts_unless_confirmed(self):
        r = self.call("SetOverdrive", "ss", "card9", '{"sclk_max": 2400, "voltage_offset": -50}')
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.od(), (2400, -50))
        boot = self.call("GetState")["cards"]["card9"]["overdrive"]["boot"]
        self.assertEqual(boot, {"sclk_max": 2509, "mclk_max": 1000, "voltage_offset": 0})
        time.sleep(self.CONFIRM + 0.7)
        self.assertEqual(self.od(), (2509, 0))

    def test_gpu_hang_restores_original_values(self):
        self.call("SetOverdrive", "ss", "card9", '{"voltage_offset": -100}')
        self.call("SetPowerLimit", "sd", "card9", 240)
        self.kernel.write("3,1234,567,-;amdgpu 0000:2d:00.0: amdgpu: ring gfx_0.0.0 timeout, signaled seq=1\n")
        self.kernel.flush()
        time.sleep(0.5)
        state = self.call("GetState")
        self.assertEqual(state["fault_count"], 1)
        self.assertIsNone(state["pending"])
        self.assertEqual(self.od(), (2509, 0))
        self.assertEqual(self.cap(), "264000000")

    def test_unrelated_kernel_messages_are_ignored(self):
        self.kernel.write("6,1,2,-;usb 1-1: new high-speed USB device\n")
        self.kernel.flush()
        time.sleep(0.3)
        self.assertEqual(self.call("GetState")["fault_count"], 0)

    def save_undervolt_profile(self):
        """Applies -70 mV, confirms it from one connection (as the UI does) and saves it for boot."""
        try:
            import dbus
        except ImportError:
            self.skipTest("needs dbus-python for a client that can confirm")
        iface = dbus.Interface(dbus.SessionBus().get_object(BUS_NAME, OBJECT_PATH), INTERFACE)
        self.assertTrue(json.loads(iface.SetOverdrive("card9", '{"voltage_offset": -70}'))["ok"])
        self.assertTrue(self.call("GetState")["cards"]["card9"]["risky"])
        self.assertFalse(json.loads(iface.SaveBootProfile("card9"))["ok"])  # still pending
        self.assertTrue(json.loads(iface.Confirm())["ok"])
        self.assertTrue(json.loads(iface.SaveBootProfile("card9"))["ok"])
        self.assertTrue(self.call("GetState")["boot_profile"]["enabled"])

    def test_boot_profile_applies_after_clean_restart(self):
        self.save_undervolt_profile()
        self.stop()                                   # clean stop restores factory values
        self.assertEqual(self.od(), (2509, 0))
        self.start()                                  # next boot
        self.assertEqual(self.od(), (2509, -70))
        state = self.call("GetState")
        self.assertTrue(state["boot_profile"]["enabled"])
        self.assertTrue(state["cards"]["card9"]["changed"])
        self.assertEqual(state["cards"]["card9"]["overdrive"]["boot"]["voltage_offset"], 0)
        self.assertTrue(state["cards"]["card9"]["is_boot_profile"])

    def test_boot_profile_skipped_after_crash(self):
        self.save_undervolt_profile()
        self.stop(crash=True)                         # freeze or power loss while applied
        self.start()
        self.assertEqual(self.od(), (2509, 0))        # restored by the crash reset, not re-applied
        profile = self.call("GetState")["boot_profile"]
        self.assertFalse(profile["enabled"])
        self.assertIn("without a clean shutdown", profile["notice"])
        self.assertTrue(self.call("EnableBootProfile")["ok"])
        self.assertTrue(self.call("GetState")["boot_profile"]["enabled"])

    def test_gpu_hang_turns_boot_profile_off(self):
        self.save_undervolt_profile()
        self.kernel.write("3,1,2,-;amdgpu 0000:2d:00.0: amdgpu: GPU reset begin!\n")
        self.kernel.flush()
        time.sleep(0.5)
        profile = self.call("GetState")["boot_profile"]
        self.assertFalse(profile["enabled"])
        self.assertIn("GPU hang", profile["notice"])
        self.stop()
        self.start()
        self.assertEqual(self.od(), (2509, 0))

    def test_clear_boot_profile(self):
        self.save_undervolt_profile()
        self.assertTrue(self.call("ClearBootProfile", "s", "card9")["ok"])
        self.assertFalse(os.path.exists(os.path.join(self.state, "profile.json")))
        self.stop()
        self.start()
        self.assertEqual(self.od(), (2509, 0))

    def test_cpu_state_and_curve_optimizer_revert(self):
        cpu = self.call("GetState")["cpu"]
        self.assertEqual(cpu["limits"], {"ppt": 142, "tdc": 95, "edc": 140})
        self.assertEqual(cpu["co"], [0] * 16)
        self.assertTrue(cpu["per_core"])
        r = self.call("SetCurveOptimizer", "s", json.dumps([-10] * 8 + [-15] * 8))
        self.assertTrue(r["ok"], r)
        cpu = self.call("GetState")["cpu"]
        self.assertEqual(cpu["co"], [-10] * 8 + [-15] * 8)
        self.assertTrue(cpu["risky"])
        time.sleep(self.CONFIRM + 0.7)
        self.assertEqual(self.call("GetState")["cpu"]["co"], [0] * 16)

    def test_cpu_limits_and_bad_requests(self):
        self.assertTrue(self.call("SetCpuLimits", "s", '{"ppt": 120, "tdc": 80}')["ok"])
        self.assertEqual(self.call("GetState")["cpu"]["limits"], {"ppt": 120, "tdc": 80, "edc": 140})
        self.assertFalse(self.call("SetCpuLimits", "s", '{"ppt": 500}')["ok"])
        self.assertFalse(self.call("SetCurveOptimizer", "s", json.dumps([5] * 16))["ok"])
        self.assertFalse(self.call("SetPowerLimit", "sd", "cpu", 100)["ok"])  # a GPU method on the CPU

    def test_machine_check_restores_cpu(self):
        self.call("SetCurveOptimizer", "s", json.dumps([-20] * 16))
        self.kernel.write("3,5,6,-;mce: [Hardware Error]: Machine check events logged\n")
        self.kernel.flush()
        time.sleep(0.5)
        state = self.call("GetState")
        self.assertEqual(state["fault_count"], 1)
        self.assertEqual(state["cpu"]["co"], [0] * 16)

    def test_invalid_curve_is_refused(self):
        r = self.call("SetFanCurve", "ss", "card9", "[[40, 60], [80, 20]]")
        self.assertFalse(r["ok"])
        self.assertEqual(fakegpu.read(f"{self.hwmon}/pwm1_enable"), "2")


if __name__ == "__main__":
    unittest.main()
