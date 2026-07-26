import os
import tempfile
import unittest

from autopa.temperature_plan import (
    build_temperature_plan, parse_temperatures)


class TemperaturePlanTest(unittest.TestCase):
    def test_plan_generates_one_safe_file_per_temperature(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_temperature_plan(
                directory, [200, 210, 220], [0.02, 0.04],
                cycles=3, restore_advance=0.03,
                material_label="test")
            self.assertEqual(len(result["files"]), 3)
            self.assertTrue(result["heating_is_not_automated"])
            for item in result["files"]:
                self.assertTrue(os.path.exists(
                    os.path.join(directory, item["gcode"])))

    def test_at_least_three_temperatures_are_required(self):
        with self.assertRaises(ValueError):
            parse_temperatures("200,210")


if __name__ == "__main__":
    unittest.main()
