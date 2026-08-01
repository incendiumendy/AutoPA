"""Bounded auto-apply policy for sweep recommendations.

A calibration-sweep recommendation may be applied at runtime only when it
stays close to the value that was active during the sweep. The deviation
limit is configurable per run but hard-capped here; the applied value is
never persisted (no SAVE_CONFIG) and a failed or inconclusive analysis
never touches the printer.
"""
import math


DEFAULT_APPLY_BOUNDS = {
    "retract": 1.5,
    "pa": 0.09,
}
MAX_APPLY_BOUNDS = {
    "retract": 3.0,
    "pa": 0.2,
}


def _finite(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value))


def validated_apply_bound(raw, kind):
    """Return a safe deviation limit for one sweep kind."""
    if kind not in DEFAULT_APPLY_BOUNDS:
        raise ValueError("unknown apply-bound kind %r" % (kind,))
    if raw is None:
        return DEFAULT_APPLY_BOUNDS[kind]
    if not _finite(raw):
        raise ValueError("apply_bound must be a finite number")
    value = float(raw)
    if not 0.0 < value <= MAX_APPLY_BOUNDS[kind]:
        raise ValueError(
            "apply_bound is outside the safe range 0..%s"
            % MAX_APPLY_BOUNDS[kind])
    return value


def apply_decision(recommended, current, bound):
    """Decide whether a recommendation may be applied at runtime."""
    if not _finite(recommended) or not _finite(current):
        return {
            "eligible": False,
            "reason": "values_unavailable",
            "recommended": None,
            "current": None,
            "deviation": None,
            "bound": float(bound),
        }
    deviation = abs(float(recommended) - float(current))
    if deviation > float(bound):
        return {
            "eligible": False,
            "reason": "outside_bounds",
            "recommended": float(recommended),
            "current": float(current),
            "deviation": deviation,
            "bound": float(bound),
        }
    return {
        "eligible": True,
        "reason": None,
        "recommended": float(recommended),
        "current": float(current),
        "deviation": deviation,
        "bound": float(bound),
    }
