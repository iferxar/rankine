import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rankine.tuned import ryzen
from rankine.tuned.gpu import TuningError
from tests.fakesmu import FakeSmu


class PmTableTest(unittest.TestCase):
    def test_reads_both_16_core_layouts(self):
        for version in (0x380804, 0x380805):
            t = FakeSmu(version).pm_table()
            self.assertEqual((t["ppt_limit"], t["tdc_limit"], t["edc_limit"]), (142, 95, 140))
            self.assertEqual(len(t["core_voltage"]), 16)
            self.assertAlmostEqual(t["core_voltage"][3], 1.2, places=5)
            self.assertEqual(t["core_freq"][0], 4500)

    def test_unknown_or_garbled_table_is_rejected(self):
        smu = FakeSmu()
        smu.version = 0x123456
        self.assertIsNone(smu.pm_table())
        smu = FakeSmu()
        smu.limits["ppt"] = 0.0001
        self.assertIsNone(smu.pm_table())


class CurveOptimizerTest(unittest.TestCase):
    def test_core_masks_follow_ccds(self):
        smu = FakeSmu()
        self.assertEqual(smu.core_mask(0), 0)
        self.assertEqual(smu.core_mask(7), 7 << 20)
        self.assertEqual(smu.core_mask(8), 1 << 28)
        self.assertEqual(smu.core_mask(15), (1 << 28) | (7 << 20))

    def test_negative_margins_round_trip(self):
        c = ryzen.RyzenControl(FakeSmu())
        c.set_curve([-10] * 8 + [-20] * 8)
        self.assertEqual(c.curve(), [-10] * 8 + [-20] * 8)

    def test_only_undervolting_and_whole_cpus(self):
        c = ryzen.RyzenControl(FakeSmu())
        for bad in ([5] * 16, [-31] * 16, [-10] * 15):
            with self.assertRaises(TuningError):
                c.set_curve(bad)
        partial = ryzen.RyzenControl(FakeSmu())
        partial.smu.ccds = [list(range(6)), list(range(6, 12))]  # 12-core part with cores fused off
        partial.smu.co = {c: 0 for c in partial.smu.all_cores}
        with self.assertRaises(TuningError):
            partial.set_curve([-10] * 6 + [-5] * 6)
        partial.set_curve([-10] * 12)  # one margin for all is fine

    def test_unreadable_margins_disable_curve_optimizer(self):
        c = ryzen.RyzenControl(FakeSmu(co_readable=False))
        self.assertFalse(c.co_readable)
        with self.assertRaises(TuningError):
            c.set_curve([-5] * 16)

    def test_restore_puts_back_bios_values(self):
        smu = FakeSmu()
        smu.co = {c: (5 if c == 3 else 0) for c in smu.all_cores}  # BIOS set +5 on one core
        c = ryzen.RyzenControl(smu)
        snap = c.snapshot()
        c.set_curve([-15] * 16)
        c.set_limits(ppt=120, tdc=80)
        c.restore(snap)
        self.assertEqual(c.snapshot(), snap)


class LimitsTest(unittest.TestCase):
    def test_range_and_units(self):
        c = ryzen.RyzenControl(FakeSmu())
        self.assertEqual(c.limit_ranges()["ppt"], [45, 213])
        c.set_limits(ppt=120)
        self.assertIn(("rsmu", ryzen.RSMU_SET_PPT, 120000), c.smu.log)
        with self.assertRaises(TuningError):
            c.set_limits(edc=500)


if __name__ == "__main__":
    unittest.main()
