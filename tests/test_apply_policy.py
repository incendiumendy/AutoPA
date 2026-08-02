import unittest

from autopa.apply_policy import (
    DEFAULT_APPLY_BOUNDS, MAX_APPLY_BOUNDS, apply_decision,
    summarize_analysis, validated_apply_bound)


class ValidatedApplyBoundTest(unittest.TestCase):
    def test_defaults_are_used_when_unset(self):
        self.assertEqual(
            validated_apply_bound(None, "retract"),
            DEFAULT_APPLY_BOUNDS["retract"])
        self.assertEqual(
            validated_apply_bound(None, "pa"),
            DEFAULT_APPLY_BOUNDS["pa"])

    def test_custom_bound_within_hard_cap_is_accepted(self):
        self.assertEqual(validated_apply_bound(0.5, "retract"), 0.5)
        self.assertEqual(validated_apply_bound(0.02, "pa"), 0.02)

    def test_bounds_beyond_hard_cap_are_rejected(self):
        for kind in ("retract", "pa"):
            with self.assertRaises(ValueError):
                validated_apply_bound(MAX_APPLY_BOUNDS[kind] + 0.01, kind)
            with self.assertRaises(ValueError):
                validated_apply_bound(0.0, kind)
            with self.assertRaises(ValueError):
                validated_apply_bound(-1.0, kind)
            with self.assertRaises(ValueError):
                validated_apply_bound("viel", kind)
            with self.assertRaises(ValueError):
                validated_apply_bound(True, kind)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            validated_apply_bound(None, "flow")


class ApplyDecisionTest(unittest.TestCase):
    def test_within_bound_is_eligible(self):
        decision = apply_decision(1.2, 0.5, 1.5)
        self.assertTrue(decision["eligible"])
        self.assertAlmostEqual(decision["deviation"], 0.7)
        self.assertIsNone(decision["reason"])

    def test_exactly_at_bound_is_eligible(self):
        decision = apply_decision(2.0, 0.5, 1.5)
        self.assertTrue(decision["eligible"])

    def test_outside_bound_is_rejected(self):
        decision = apply_decision(2.6, 0.5, 1.5)
        self.assertFalse(decision["eligible"])
        self.assertEqual(decision["reason"], "outside_bounds")
        self.assertAlmostEqual(decision["deviation"], 2.1)

    def test_missing_values_fail_closed(self):
        for recommended, current in ((None, 0.5), (1.0, None), (None, None)):
            decision = apply_decision(recommended, current, 1.5)
            self.assertFalse(decision["eligible"])
            self.assertEqual(decision["reason"], "values_unavailable")


if __name__ == "__main__":
    unittest.main()


class SummarizeAnalysisTest(unittest.TestCase):
    """The chart needs the whole curve, not just the winner."""

    def pa_result(self, costs):
        return {
            "per_k": [
                {"k": k, "cost": cost, "cycles_included": 4,
                 "cycles_total": 5}
                for k, cost in costs
            ],
            "quality_gate_passed": True,
        }

    def test_winner_at_the_range_edge_is_flagged(self):
        # This is the real case from the printer: the lowest cost sat on the
        # last measured value, so the true optimum may lie outside the sweep.
        summary = summarize_analysis(self.pa_result([
            (0.01, 0.2153), (0.05, 0.3830), (0.09, 0.0783)]))
        self.assertEqual(summary["best"], 0.09)
        self.assertTrue(summary["bestAtRangeEdge"])
        self.assertEqual(len(summary["points"]), 3)

    def test_winner_inside_the_range_is_not_flagged(self):
        summary = summarize_analysis(self.pa_result([
            (0.01, 0.40), (0.05, 0.08), (0.09, 0.35)]))
        self.assertEqual(summary["best"], 0.05)
        self.assertFalse(summary["bestAtRangeEdge"])

    def test_retract_speed_curve_keeps_its_own_variable(self):
        summary = summarize_analysis({
            "swept_variable": "retract_speed",
            "per_value": [
                {"swept_value": 20.0, "cost": 0.08, "cycles_included": 4},
                {"swept_value": 40.0, "cost": 0.21, "cycles_included": 5},
            ],
            "quality_gate_passed": True,
        })
        self.assertEqual(summary["sweptVariable"], "retract_speed")
        self.assertEqual(summary["best"], 20.0)

    def test_values_without_a_cost_are_kept_as_gaps(self):
        # A candidate with too few usable cycles has no cost. Dropping it
        # would hide that part of the range failed entirely.
        summary = summarize_analysis({
            "per_value": [
                {"swept_value": 0.2, "cost": 0.3, "cycles_included": 5},
                {"swept_value": 0.8, "cost": None, "cycles_included": 0},
            ],
            "quality_gate_passed": True,
        })
        self.assertEqual(len(summary["points"]), 2)
        self.assertIsNone(summary["points"][1]["cost"])
        self.assertEqual(summary["best"], 0.2)

    def test_empty_or_unusable_results_summarize_to_nothing(self):
        self.assertIsNone(summarize_analysis(None))
        self.assertIsNone(summarize_analysis({}))
        self.assertIsNone(summarize_analysis({"per_k": []}))
