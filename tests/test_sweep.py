import unittest

from autopa.sweep import build_sweep, decimal_range


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

    def test_target_temperature_is_validated_in_gcode(self):
        gcode, plan = build_sweep(
            [0.02], cycles=3, restore_advance=0.03,
            target_temperature=215, temperature_tolerance=1.5)
        self.assertIn(
            "TARGET_TEMP=215.00 TEMP_TOLERANCE=1.50", gcode)
        self.assertEqual(plan["target_temperature_c"], 215)


if __name__ == "__main__":
    unittest.main()
