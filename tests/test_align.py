import csv
import json
import os
import pathlib
import sys
import tempfile
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))
from autopa.align import (
    align_dataset, extruder_state_at, interpolate, linear_fit,
    regularize_sample_times)


class AlignmentTest(unittest.TestCase):
    def test_regularize_force_sample_times(self):
        regularized, diagnostics = regularize_sample_times(
            [1.0, 1.0011, 1.0019, 1.0031])
        deltas = [
            right - left
            for left, right in zip(regularized, regularized[1:])
        ]
        self.assertAlmostEqual(deltas[0], deltas[1], places=12)
        self.assertAlmostEqual(deltas[1], deltas[2], places=12)
        self.assertEqual(
            diagnostics["force_timestamp_model"], "sample_index_linear_fit")
        self.assertAlmostEqual(
            diagnostics["force_sample_rate_model_hz"], 1000.0, delta=30.0)
        self.assertGreater(
            diagnostics["force_arrival_max_residual_ms"], 0.0)

    def test_linear_fit(self):
        slope, offset, rms, maximum = linear_fit(
            [(1.0, 12.0), (2.0, 14.0), (3.0, 16.0)])
        self.assertAlmostEqual(slope, 2.0)
        self.assertAlmostEqual(offset, 10.0)
        self.assertAlmostEqual(rms, 0.0)
        self.assertAlmostEqual(maximum, 0.0)

    def test_interpolate(self):
        self.assertAlmostEqual(
            interpolate([1.0, 2.0], [10.0, 20.0], 1.25), 12.5)

    def test_interpolate_rejects_outside_range(self):
        self.assertIsNone(interpolate([1.0, 2.0], [10.0, 20.0], 0.5))
        self.assertIsNone(interpolate([1.0, 2.0], [10.0, 20.0], 2.5))

    def test_alignment_adds_calibrated_force_without_changing_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "clock_sync.csv"),
                      "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow((
                    "request_host_monotonic_ns",
                    "response_host_monotonic_ns",
                    "klipper_host_monotonic", "print_time"))
                writer.writerow((0, 0, 1.0, 11.0))
                writer.writerow((0, 0, 3.0, 13.0))
            with open(os.path.join(directory, "force.csv"),
                      "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("host_monotonic_ns", "raw", "filtered"))
                writer.writerow((1000000000, 1000, 1000))
                writer.writerow((2000000000, 1100, 1100))
                writer.writerow((3000000000, 1200, 1200))
            with open(os.path.join(directory, "acceleration.csv"),
                      "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow((
                    "print_time", "x_mm_s2", "y_mm_s2", "z_mm_s2"))
                writer.writerow((11.5, 0, 0, -9810))
                writer.writerow((12.5, 0, 0, -9810))
            calibration_path = os.path.join(directory, "calibration.json")
            with open(calibration_path, "w") as handle:
                json.dump({
                    "offset_counts": 1000,
                    "counts_per_gram": 100,
                    "calibration_id": "test-calibration",
                    "valid": True,
                }, handle)
            result = align_dataset(directory, calibration_path)
            self.assertEqual(result["force_unit"], "grams")
            with open(os.path.join(directory, "combined.csv"),
                      newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["force_filtered"], "1050.000000")
            self.assertEqual(rows[0]["force_filtered_grams"], "0.500000000")

    def test_alignment_without_accelerometer_uses_force_timebase(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "clock_sync.csv"),
                      "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow((
                    "request_host_monotonic_ns",
                    "response_host_monotonic_ns",
                    "klipper_host_monotonic", "print_time"))
                writer.writerow((0, 0, 1.0, 11.0))
                writer.writerow((0, 0, 3.0, 13.0))
            with open(os.path.join(directory, "force.csv"),
                      "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("host_monotonic_ns", "raw", "filtered"))
                writer.writerow((1000000000, 1000, 900))
                writer.writerow((2000000000, 1100, 1000))
                writer.writerow((3000000000, 1200, 1100))
            with open(os.path.join(directory, "acceleration.csv"),
                      "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow((
                    "print_time", "x_mm_s2", "y_mm_s2", "z_mm_s2"))

            result = align_dataset(directory)

            self.assertFalse(result["acceleration_available"])
            with open(os.path.join(directory, "combined.csv"),
                      newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(3, len(rows))
            self.assertEqual("", rows[0]["x_mm_s2"])

    def test_extruder_velocity_is_reconstructed(self):
        segments = [{
            "print_time": 10.0,
            "duration_s": 2.0,
            "start_velocity_mm_s": 1.0,
            "acceleration_mm_s2": 2.0,
            "direction": 1.0,
            "pressure_advance_active": True,
        }]
        velocity, pa_active, index = extruder_state_at(
            segments, 10.5)
        self.assertAlmostEqual(velocity, 2.0)
        self.assertTrue(pa_active)
        self.assertEqual(index, 0)


if __name__ == "__main__":
    unittest.main()
