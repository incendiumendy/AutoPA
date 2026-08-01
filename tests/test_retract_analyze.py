import csv
import json
import math
import os
import tempfile
import unittest

from autopa.retract_analyze import analyze_retract_dataset, cycle_metrics


SAMPLE_RATE = 200.0
EXTRUDE_S = 1.2
DWELL_S = 1.0
RESTART_S = 1.0
GAP_S = 0.3
EXTRUSION_LEVEL = 120.0


def _residual(retract_length):
    return max(0.0, EXTRUSION_LEVEL * (1.0 - retract_length / 1.2))


def _dip(retract_length):
    return max(0.0, (retract_length - 1.0) * 80.0)


def _force_at(time_s, cycles):
    for retract_time, unretract_time, cycle_end, length in cycles:
        if retract_time - EXTRUDE_S <= time_s < retract_time:
            return EXTRUSION_LEVEL
        if retract_time <= time_s < unretract_time:
            residual = _residual(length)
            return residual + (EXTRUSION_LEVEL - residual) * math.exp(
                -(time_s - retract_time) / 0.15)
        if unretract_time <= time_s < cycle_end:
            return EXTRUSION_LEVEL - _dip(length) * math.exp(
                -(time_s - unretract_time) / 0.2)
    return 0.0


def _write_dataset(directory, retract_lengths=(0.2, 0.8, 1.4),
                   cycles_per_value=3, with_quality=True):
    cycles = []
    events = []
    sequence = 0

    def mark(print_time, event, value=""):
        nonlocal sequence
        sequence += 1
        events.append({
            "sequence": sequence,
            "print_time": print_time,
            "event": event,
            "value": value,
        })

    mark(0.0, "retract_sweep_start", "%.4f" % retract_lengths[0])
    now = 0.0
    for length in retract_lengths:
        mark(now, "r_start", "%.4f" % length)
        for cycle in range(cycles_per_value):
            value = "%.4f:%d" % (length, cycle)
            retract_time = now + EXTRUDE_S
            unretract_time = retract_time + DWELL_S
            cycle_end = unretract_time + RESTART_S
            cycles.append((retract_time, unretract_time, cycle_end, length))
            mark(retract_time, "retract_start", value)
            mark(unretract_time, "unretract_start", value)
            mark(cycle_end, "cycle_end", value)
            now = cycle_end + GAP_S
        mark(now, "r_end", "%.4f" % length)
    mark(now, "retract_sweep_end", "%.4f" % retract_lengths[-1])

    with open(os.path.join(directory, "combined.csv"), "w",
              newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["print_time", "force_filtered"])
        sample_count = int((now + 0.5) * SAMPLE_RATE)
        for index in range(sample_count):
            time_s = index / SAMPLE_RATE
            writer.writerow(["%.5f" % time_s, "%.6f" % _force_at(time_s, cycles)])
    with open(os.path.join(directory, "events.csv"), "w",
              newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["sequence", "print_time", "event", "value"])
        writer.writeheader()
        for event in events:
            writer.writerow(event)
    if with_quality:
        with open(os.path.join(directory, "quality.json"), "w") as handle:
            json.dump({"analysis_eligible": True}, handle)


class RetractAnalyzeTest(unittest.TestCase):
    def test_recommendation_prefers_balanced_length(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_dataset(directory)
            result = analyze_retract_dataset(directory)
        self.assertTrue(result["quality_gate_passed"])
        self.assertEqual(result["retract_cycle_count"], 9)
        recommendation = result["recommendation"]
        self.assertIsNotNone(recommendation)
        self.assertEqual(recommendation["retract_length_mm"], 0.8)
        self.assertFalse(recommendation["apply_automatically"])
        self.assertTrue(recommendation["experimental"])
        self.assertEqual(result["printer_action"], "none")
        per_value = {
            item["retract_length_mm"]: item for item in result["per_value"]}
        self.assertEqual(per_value[0.8]["cycles_included"], 3)
        short = per_value[0.2]["medians"]
        long = per_value[1.4]["medians"]
        self.assertGreater(short["residual_counts"], long["residual_counts"])
        self.assertGreater(
            long["restart_deficit_ratio"],
            per_value[0.8]["medians"]["restart_deficit_ratio"])

    def test_missing_quality_gate_suppresses_recommendation(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_dataset(directory, with_quality=False)
            result = analyze_retract_dataset(directory)
        self.assertFalse(result["quality_gate_passed"])
        self.assertIsNone(result["recommendation"])
        self.assertEqual(len(result["per_value"]), 3)

    def test_cycle_metrics_rejects_short_dwell(self):
        rows = [
            {"print_time": index / SAMPLE_RATE, "force": 100.0,
             "x_mm_s2": None, "y_mm_s2": None, "z_mm_s2": None}
            for index in range(400)
        ]
        result = cycle_metrics(rows, 1.0, 1.4, 2.0)
        self.assertFalse(result["included"])
        self.assertEqual(result["reason"], "dwell_too_short")


if __name__ == "__main__":
    unittest.main()
