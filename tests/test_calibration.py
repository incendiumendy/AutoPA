import csv
import json
import os
import tempfile
import unittest

from autopa.calibration import (
    build_calibration, counts_to_grams, load_calibration)


def write_capture(path, center, noise):
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("host_monotonic_ns", "raw", "filtered"))
        for index in range(200):
            value = center + ((index % 5) - 2) * noise
            writer.writerow((index * 1000000, value, value))


class CalibrationTest(unittest.TestCase):
    def test_positive_three_point_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            zero = os.path.join(directory, "zero.csv")
            hundred = os.path.join(directory, "100.csv")
            two_hundred = os.path.join(directory, "200.csv")
            write_capture(zero, 1000000, 2)
            write_capture(hundred, 1050000, 2)
            write_capture(two_hundred, 1100000, 2)
            result = build_calibration(
                zero, [(100, hundred), (200, two_hundred)])
            self.assertTrue(result["valid"])
            self.assertEqual(result["polarity"], "increasing")
            self.assertAlmostEqual(result["counts_per_gram"], 500.0)
            self.assertAlmostEqual(
                counts_to_grams(1075000, result), 150.0)

    def test_negative_polarity_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            zero = os.path.join(directory, "zero.csv")
            loaded = os.path.join(directory, "loaded.csv")
            write_capture(zero, 1000000, 2)
            write_capture(loaded, 950000, 2)
            result = build_calibration(zero, [(100, loaded)])
            self.assertTrue(result["valid"])
            self.assertEqual(result["polarity"], "decreasing")
            self.assertAlmostEqual(
                counts_to_grams(975000, result), 50.0)

    def test_invalid_file_is_rejected(self):
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False) as handle:
            json.dump({
                "offset_counts": 1,
                "counts_per_gram": 2,
                "calibration_id": "bad",
                "valid": False,
            }, handle)
            path = handle.name
        try:
            with self.assertRaises(ValueError):
                load_calibration(path)
        finally:
            os.unlink(path)

    def test_reference_span_must_exceed_noise(self):
        with tempfile.TemporaryDirectory() as directory:
            zero = os.path.join(directory, "zero.csv")
            loaded = os.path.join(directory, "loaded.csv")
            write_capture(zero, 1000000, 100)
            write_capture(loaded, 1000500, 100)
            with self.assertRaises(ValueError):
                build_calibration(zero, [(100, loaded)])


if __name__ == "__main__":
    unittest.main()
