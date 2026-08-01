import unittest

from autopa.sweep import build_sweep, decimal_range, prime_settle_e


class SweepTest(unittest.TestCase):
    def test_decimal_range_includes_stop(self):
        self.assertEqual(
            decimal_range(0.0, 0.04, 0.01),
            [0.0, 0.01, 0.02, 0.03, 0.04])

    def test_sweep_returns_to_start_each_cycle(self):
        gcode, plan = build_sweep(
            [0.0, 0.02], cycles=3, restore_advance=0.04)
        self.assertEqual(gcode.count("G1 X8.0000"), 6)
        self.assertEqual(gcode.count("G1 X-8.0000"), 6)
        self.assertIn(
            "SET_PRESSURE_ADVANCE ADVANCE=0.040000", gcode)
        self.assertEqual(plan["estimated_sweep_duration_s"], 7.5)
        self.assertAlmostEqual(plan["filament_length_mm"], 16.8)

    def test_restore_advance_is_required(self):
        with self.assertRaises(ValueError):
            build_sweep([0.0], cycles=3)

    def test_rejects_unbounded_values(self):
        with self.assertRaises(ValueError):
            build_sweep([0.3], cycles=3, restore_advance=0.0)
        with self.assertRaises(ValueError):
            build_sweep(
                [0.0], cycles=3, x_travel=31, restore_advance=0.0)

    def test_prime_settle_stays_within_its_bounds(self):
        self.assertEqual(prime_settle_e(0.0), 0.0)
        self.assertEqual(prime_settle_e(None), 0.0)
        # Below the lower bound a tiny prime still gets a usable settle.
        self.assertEqual(prime_settle_e(0.5), 1.0)
        self.assertEqual(prime_settle_e(4.0), 1.0)
        # Inside the band the settle is a quarter of the prime.
        self.assertAlmostEqual(prime_settle_e(10.0), 2.5)
        # At the top of the allowed prime range the cap applies.
        self.assertEqual(prime_settle_e(20.0), 4.0)

    def test_settle_extrusion_follows_the_main_prime(self):
        gcode, plan = build_sweep(
            [0.02], cycles=3, restore_advance=0.03, start_z=50.0,
            prime_e=10.0, current_z=0.0)
        self.assertEqual(plan["prime_settle_e_mm"], 2.5)
        main = gcode.index("G1 E10.00000 F300")
        settle = gcode.index("G1 E2.50000 F120")
        self.assertLess(main, settle)
        # The settle volume is part of the reported filament budget.
        self.assertAlmostEqual(plan["filament_length_mm"], 8.4 + 10.0 + 2.5)

    def test_no_prime_emits_no_settle_extrusion(self):
        gcode, plan = build_sweep(
            [0.02], cycles=3, restore_advance=0.03, prime_e=0.0)
        self.assertEqual(plan["prime_settle_e_mm"], 0.0)
        self.assertNotIn("F120", gcode)

    def test_target_temperature_is_validated_in_gcode(self):
        gcode, plan = build_sweep(
            [0.02], cycles=3, restore_advance=0.03,
            target_temperature=215, temperature_tolerance=1.5)
        self.assertIn(
            "TARGET_TEMP=215.00 TEMP_TOLERANCE=1.50", gcode)
        self.assertEqual(plan["target_temperature_c"], 215)


if __name__ == "__main__":
    unittest.main()
