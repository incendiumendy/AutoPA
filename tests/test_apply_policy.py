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


class NoResultDiagnosisTest(unittest.TestCase):
    """"No result" must name a cause, not imply a safety refusal."""

    def dataset(self):
        # Shaped like the real PA analysis that produced no ranking: the
        # quality gate passed, but most cycles were below the noise floor.
        return {
            "quality_gate_passed": True,
            "per_k": [
                {
                    "k": 0.01 * (index + 1),
                    "cost": None,
                    "cycles_included": 2,
                    "cycles_total": 5,
                    "cycles": (
                        [{"included": True}] * 2
                        + [{
                            "included": False,
                            "reason": "step_amplitude_below_3x_baseline_mad",
                        }] * 3
                    ),
                }
                for index in range(9)
            ],
        }

    def test_counts_and_names_the_rejections(self):
        summary = summarize_analysis(self.dataset())
        self.assertEqual(summary["cyclesTotal"], 45)
        self.assertEqual(summary["cyclesIncluded"], 18)
        self.assertEqual(
            summary["rejectedReasons"][0],
            {"reason": "step_amplitude_below_3x_baseline_mad", "count": 27})
        # Nothing was rankable, which is why the pipeline had no
        # recommendation to report.
        self.assertEqual(summary["rankableValues"], 0)
        # And it was not the safety gate: that passed.
        self.assertTrue(summary["qualityGatePassed"])

    def test_a_healthy_run_reports_no_rejections(self):
        summary = summarize_analysis({
            "quality_gate_passed": True,
            "per_k": [
                {"k": 0.02, "cost": 0.3, "cycles_included": 5,
                 "cycles_total": 5, "cycles": [{"included": True}] * 5},
                {"k": 0.04, "cost": 0.1, "cycles_included": 5,
                 "cycles_total": 5, "cycles": [{"included": True}] * 5},
                {"k": 0.06, "cost": 0.4, "cycles_included": 5,
                 "cycles_total": 5, "cycles": [{"included": True}] * 5},
            ],
        })
        self.assertEqual(summary["rejectedReasons"], [])
        self.assertEqual(summary["cyclesIncluded"], summary["cyclesTotal"])
        self.assertEqual(summary["rankableValues"], 3)


class SignalVerdictTest(unittest.TestCase):
    """A weak run that still ranks is the dangerous case, not the failed one."""

    def run_with(self, kept, total, values=5, gap=0.2):
        per_value = []
        for index in range(values):
            per_value.append({
                "swept_value": 0.01 * (index + 1),
                "cost": 0.1 * (index + 1),
                "cycles_included": kept,
                "cycles_total": total,
                "cycles": (
                    [{"included": True}] * kept
                    + [{"included": False, "reason": "weak"}] * (total - kept)
                ),
            })
        return {
            "quality_gate_passed": True,
            "per_value": per_value,
            "recommendation": {"cost_gap_to_second_best": gap},
        }

    def test_a_clean_run_needs_no_repeat(self):
        signal = summarize_analysis(self.run_with(5, 5))["signal"]
        self.assertEqual(signal["state"], "ok")
        self.assertFalse(signal["repeatAdvised"])
        self.assertEqual(signal["keptRatio"], 1.0)

    def test_mostly_rejected_cycles_are_called_weak(self):
        # Matches the printer: 27 of 45 cycles kept, a winner was still
        # reported, and the next run named a different one.
        signal = summarize_analysis(self.run_with(3, 5))["signal"]
        self.assertEqual(signal["state"], "weak")
        self.assertTrue(signal["repeatAdvised"])

    def test_too_few_rankable_values_is_insufficient(self):
        signal = summarize_analysis(self.run_with(5, 5, values=2))["signal"]
        self.assertEqual(signal["state"], "insufficient")
        self.assertTrue(signal["repeatAdvised"])

    def test_a_close_winner_is_flagged_even_on_a_clean_run(self):
        # Every cycle usable, but the margin is inside single-run scatter.
        signal = summarize_analysis(self.run_with(5, 5, gap=0.01))["signal"]
        self.assertEqual(signal["state"], "close")
        self.assertTrue(signal["repeatAdvised"])

    def test_no_cycles_at_all_stays_unknown(self):
        signal = summarize_analysis({
            "quality_gate_passed": True,
            "per_value": [{"swept_value": 0.2, "cost": 0.1}],
        })["signal"]
        self.assertEqual(signal["state"], "unknown")
        self.assertFalse(signal["repeatAdvised"])
