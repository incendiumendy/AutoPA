import unittest

from autopa.retract_sweep import build_retract_sweep
from autopa.sweep import decimal_range


class RetractSweepTest(unittest.TestCase):
    def test_decimal_range_includes_stop(self):
        self.assertEqual(
            decimal_range(0.2, 0.6, 0.1),
            [0.2, 0.3, 0.4, 0.5, 0.6])

    def test_sweep_structure_and_restore(self):
        gcode, plan = build_retract_sweep(
            [0.4, 0.8], cycles=3, restore_retract=0.6)
        self.assertEqual(gcode.count("\nG10\n"), 6)
        self.assertEqual(gcode.count("\nG11\n"), 6)
        self.assertEqual(gcode.count("SET_RETRACTION RETRACT_LENGTH="), 3)
        self.assertIn(
            "SET_RETRACTION RETRACT_LENGTH=0.6000", gcode)
        self.assertIn("UNRETRACT_EXTRA_LENGTH=0", gcode)
        self.assertIn("AUTOPA_VALIDATE X_TRAVEL=8.0000 MIN_Z=10.0000", gcode)
        self.assertIn("AUTOPA_MARK EVENT=retract_start VALUE=0.8000:2", gcode)
        self.assertTrue(plan["firmware_retraction_required"])
        cycle_period = 2 * 1.2 + 1.0 + 2 * 0.8 / 35.0
        self.assertAlmostEqual(
            plan["estimated_sweep_duration_s"],
            3 * (2 * 1.2 + 1.0 + 2 * 0.4 / 35.0) + 3 * cycle_period)
        self.assertAlmostEqual(plan["filament_length_mm"], 2 * 3 * 2 * 1.8)

    def test_restore_retract_is_required(self):
        with self.assertRaises(ValueError):
            build_retract_sweep([0.4], cycles=3)

    def test_rejects_unbounded_values(self):
        with self.assertRaises(ValueError):
            build_retract_sweep([10.1], cycles=3, restore_retract=0.5)
        with self.assertRaises(ValueError):
            build_retract_sweep([-0.1], cycles=3, restore_retract=0.5)
        with self.assertRaises(ValueError):
            build_retract_sweep(
                [0.4], cycles=2, restore_retract=0.5)
        with self.assertRaises(ValueError):
            build_retract_sweep(
                [0.4], cycles=3, x_travel=31, restore_retract=0.5)
        with self.assertRaises(ValueError):
            build_retract_sweep(
                [0.4], cycles=3, settle_s=0.5, restore_retract=0.5)
        with self.assertRaises(ValueError):
            build_retract_sweep(
                [0.4], cycles=3, extrude_duration=0.5, restore_retract=0.5)

    def test_target_temperature_is_validated_in_gcode(self):
        gcode, plan = build_retract_sweep(
            [0.4], cycles=3, restore_retract=0.6,
            target_temperature=215, temperature_tolerance=1.5)
        self.assertIn(
            "TARGET_TEMP=215.00 TEMP_TOLERANCE=1.50", gcode)
        self.assertEqual(plan["target_temperature_c"], 215)


if __name__ == "__main__":
    unittest.main()
