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


def summarize_analysis(result):
    """Compact per-candidate curve for the dashboard chart.

    A single recommended number reads as authoritative even when the cost
    curve behind it is noisy or its winner sits at the edge of the swept
    range, where the real optimum may lie outside what was measured. The
    chart needs the whole curve to show that.
    """
    if not isinstance(result, dict):
        return None
    entries = result.get("per_value") or result.get("per_k") or []
    points = []
    for entry in entries:
        value = entry.get("swept_value")
        if value is None:
            value = entry.get("k")
        if value is None:
            value = entry.get("retract_length_mm")
        if value is None:
            continue
        points.append({
            "value": value,
            "cost": entry.get("cost"),
            "cyclesIncluded": entry.get("cycles_included"),
            "cyclesTotal": entry.get("cycles_total"),
        })
    if not points:
        return None
    # Why cycles were thrown away. Without this the card could only say
    # "no result", which reads as a deliberate safety refusal even when the
    # quality gate passed and the real cause was a weak pressure signal the
    # operator can do something about.
    rejected = {}
    for entry in entries:
        for cycle in entry.get("cycles") or []:
            if cycle.get("included"):
                continue
            reason = cycle.get("reason") or "unknown"
            rejected[reason] = rejected.get(reason, 0) + 1
    cycles_total = sum(
        (entry.get("cycles_total") or 0) for entry in entries)
    cycles_included = sum(
        (entry.get("cycles_included") or 0) for entry in entries)

    ranked = [p for p in points if p["cost"] is not None]
    best = min(ranked, key=lambda p: p["cost"])["value"] if ranked else None
    edges = {points[0]["value"], points[-1]["value"]}
    return {
        "sweptVariable": result.get("swept_variable") or (
            "pressure_advance" if result.get("per_k") else "retract_length"),
        "points": points,
        "best": best,
        # A winner at either end usually means the optimum is outside the
        # tested window, so the range should be widened and re-run.
        "bestAtRangeEdge": best is not None and best in edges,
        "qualityGatePassed": bool(result.get("quality_gate_passed")),
        "cyclesTotal": cycles_total,
        "cyclesIncluded": cycles_included,
        # Most common rejection first, so the card can name the one that
        # actually cost the measurement its result.
        "rejectedReasons": sorted(
            ({"reason": reason, "count": count}
             for reason, count in rejected.items()),
            key=lambda item: -item["count"]),
        # The ranking needs at least three values that each kept at least
        # three cycles; below that there is nothing to compare.
        "rankableValues": len(ranked),
        "signal": _signal_verdict(
            cycles_total, cycles_included, len(ranked), result),
    }


# Below this share of usable cycles a result rests on thin evidence: it may
# still rank, but a repeat run can easily name a different winner. Observed
# on the validated printer, where three runs of the same sweep recommended
# 0.07, 0.03 and 0.09 in turn.
WEAK_SIGNAL_RATIO = 0.7
MIN_RANKABLE_VALUES = 3


def _signal_verdict(cycles_total, cycles_included, rankable, result):
    """How much the measurement itself can be trusted."""
    if not cycles_total:
        return {"state": "unknown", "keptRatio": None, "repeatAdvised": False}
    ratio = cycles_included / float(cycles_total)
    recommendation = result.get("recommendation") or {}
    gap = recommendation.get("cost_gap_to_second_best")
    if rankable < MIN_RANKABLE_VALUES:
        state = "insufficient"
    elif ratio < WEAK_SIGNAL_RATIO:
        state = "weak"
    elif gap is not None and gap < 0.05:
        # A winner this close to the runner-up is inside the noise of a
        # single run even when every cycle was usable.
        state = "close"
    else:
        state = "ok"
    return {
        "state": state,
        "keptRatio": round(ratio, 3),
        "costGapToSecondBest": gap,
        # Pooling several runs is what analyze_combined_datasets exists for.
        "repeatAdvised": state in ("insufficient", "weak", "close"),
    }
