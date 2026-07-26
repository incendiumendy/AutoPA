import math
import unittest

from autopa.analyze import _rank_pressure_advance, cycle_metrics


def synthetic_rows(overshoot):
    rows = []
    step = 0.005
    for index in range(int(1.7 / step)):
        time = index * step
        force = 1000.0
        if 0.5 <= time < 0.75:
            elapsed = time - 0.5
            force = 2000.0 - 1000.0 * math.exp(-elapsed / 0.025)
            force += overshoot * math.exp(
                -((elapsed - 0.04) / 0.015) ** 2)
        elif 0.75 <= time:
            elapsed = time - 0.75
            force = 1000.0 + 1000.0 * math.exp(-elapsed / 0.025)
        rows.append({
            "print_time": time,
            "force": force,
            "x_mm_s2": 0.0,
            "y_mm_s2": 0.0,
            "z_mm_s2": -9810.0,
        })
    return rows


class AnalyzeTest(unittest.TestCase):
    def test_combined_cycles_can_be_ranked(self):
        per_k = []
        for k_value, offset in ((0.01, 0.8), (0.03, 0.1), (0.05, 0.4)):
            per_k.append({
                "k": k_value,
                "cycles_included": 3,
                "medians": {
                    "overshoot_ratio": offset,
                    "undershoot_ratio": offset,
                    "rise_error_area_s": offset,
                    "fall_error_area_s": offset,
                },
            })
        result = _rank_pressure_advance(per_k, True)
        self.assertEqual(0.03, result["pressure_advance"])
        self.assertFalse(result["apply_automatically"])

    def test_overshoot_metric_increases(self):
        clean = cycle_metrics(synthetic_rows(0.0), 0.5, 0.75, 1.5)
        ringing = cycle_metrics(synthetic_rows(700.0), 0.5, 0.75, 1.5)
        self.assertTrue(clean["included"])
        self.assertTrue(ringing["included"])
        self.assertGreater(
            ringing["overshoot_ratio"], clean["overshoot_ratio"])

    def test_small_step_is_rejected(self):
        rows = synthetic_rows(0.0)
        for index, row in enumerate(rows):
            row["force"] = 1000.0 + (index % 7) * 10.0
        result = cycle_metrics(rows, 0.5, 0.75, 1.5)
        self.assertFalse(result["included"])


if __name__ == "__main__":
    unittest.main()
