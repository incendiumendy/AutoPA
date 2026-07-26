import math
import unittest

from autopa.quality import _gap_stats, _sample_rate, _series_stats


class QualityTest(unittest.TestCase):
    def test_series_stats(self):
        result = _series_stats([1.0, 2.0, 3.0])
        self.assertEqual(result["median"], 2.0)
        self.assertEqual(result["peak_to_peak"], 2.0)
        self.assertAlmostEqual(
            result["standard_deviation"], math.sqrt(2.0 / 3.0))

    def test_sample_rate_uses_time_span(self):
        self.assertEqual(_sample_rate([10.0, 10.5, 11.0]), 2.0)
        self.assertIsNone(_sample_rate([10.0]))

    def test_gap_stats_detects_missing_window(self):
        result = _gap_stats(
            [0.0, 0.001, 0.002, 0.003, 0.050, 0.051], 0.005)
        self.assertEqual(result["gaps_above_threshold"], 1)


if __name__ == "__main__":
    unittest.main()
