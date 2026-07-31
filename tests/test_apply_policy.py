import unittest

from autopa.apply_policy import (
    DEFAULT_APPLY_BOUNDS, MAX_APPLY_BOUNDS, apply_decision,
    validated_apply_bound)


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
