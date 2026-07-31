"""Experimental residual-pressure analysis for AutoPA retraction sweeps.

Ranks retract lengths by three direction-normalized measurements per cycle:

- residual nozzle pressure while dwelling after G10 (lower is better);
- restart pressure deficit after G11 (lower is better);
- restart pressure overshoot after G11 (lower is better).

The analysis is fail-closed: weak pressure amplitude, short dwells, too few
cycles or a failed quality gate suppress the recommendation, which is never
applied automatically.
"""
import argparse
import json
import math
import os
import statistics

from .analyze import (
    _load_combined, _load_events, _mad, _mean_square_motion, _median)


def _window(rows, start, stop):
    return [
        row["force"] for row in rows
        if start <= row["print_time"] <= stop
    ]


def cycle_metrics(rows, retract_time, unretract_time, cycle_end_time):
    """Return direction-normalized metrics for one G10/dwell/G11 cycle."""
    dwell = unretract_time - retract_time
    if dwell < 0.5:
        return {"included": False, "reason": "dwell_too_short"}
    pre = _window(rows, retract_time - 0.45, retract_time - 0.10)
    settle = _window(rows, unretract_time - 0.40, unretract_time - 0.05)
    restart_stop = min(cycle_end_time - 0.05, unretract_time + 0.60)
    restart = _window(rows, unretract_time + 0.05, restart_stop)
    early = _window(rows, unretract_time + 0.05, unretract_time + 0.40)
    if min(len(pre), len(settle), len(restart), len(early)) < 4:
        return {"included": False, "reason": "insufficient_samples"}

    raw_extrusion = _median(pre)
    raw_settle = _median(settle)
    amplitude = raw_extrusion - raw_settle
    # Pre and settle sit at deliberately different pressure levels, so their
    # noise must be estimated per window instead of over the combined list.
    noise_mad = max(_mad(pre) or 0.0, _mad(settle) or 0.0)
    if abs(amplitude) < max(1.0, 3.0 * (noise_mad or 0.0)):
        return {
            "included": False,
            "reason": "pressure_amplitude_below_3x_noise_mad",
            "amplitude": abs(amplitude),
            "noise_mad": noise_mad,
        }
    direction = 1.0 if amplitude > 0 else -1.0
    amplitude = abs(amplitude)
    oriented = lambda value: direction * value

    extrusion_level = oriented(raw_extrusion)
    settle_level = oriented(raw_settle)
    restart_min = min(oriented(value) for value in restart)
    early_max = max(oriented(value) for value in early)
    return {
        "included": True,
        "amplitude": amplitude,
        "noise_mad": noise_mad,
        "residual_counts": settle_level,
        "residual_ratio": (
            settle_level / extrusion_level if extrusion_level > 0 else None),
        "restart_deficit_ratio": max(
            0.0, extrusion_level - restart_min) / amplitude,
        "restart_overshoot_ratio": max(
            0.0, early_max - extrusion_level) / amplitude,
        "motion_rms_mm_s2": _mean_square_motion(
            rows, retract_time - 0.05, cycle_end_time),
    }


def _aggregate(cycles):
    metric_names = (
        "amplitude", "noise_mad", "residual_counts", "residual_ratio",
        "restart_deficit_ratio", "restart_overshoot_ratio",
        "motion_rms_mm_s2",
    )
    included = [cycle for cycle in cycles if cycle.get("included")]
    medians = {}
    mads = {}
    for name in metric_names:
        values = [
            cycle[name] for cycle in included
            if cycle.get(name) is not None]
        medians[name] = _median(values)
        mads[name] = _mad(values)
    return {
        "cycles_total": len(cycles),
        "cycles_included": len(included),
        "medians": medians,
        "mads": mads,
    }


def _rank_retract_lengths(per_value, allow_recommendation):
    cost_metrics = (
        "residual_counts", "restart_deficit_ratio",
        "restart_overshoot_ratio")
    eligible = [
        result for result in per_value if result["cycles_included"] >= 3]
    for result in per_value:
        result["cost"] = None
    if len(eligible) >= 3:
        normalized = {id(result): [] for result in eligible}
        for metric in cost_metrics:
            values = [result["medians"][metric] for result in eligible]
            if any(value is None for value in values):
                continue
            low, high = min(values), max(values)
            for result, value in zip(eligible, values):
                score = 0.0 if high == low else (value - low) / (high - low)
                normalized[id(result)].append(score)
        for result in eligible:
            scores = normalized[id(result)]
            if len(scores) >= 2:
                result["cost"] = statistics.fmean(scores)

    ranked = sorted(
        (result for result in eligible if result["cost"] is not None),
        key=lambda result: result["cost"])
    if not ranked or not allow_recommendation:
        return None
    best = ranked[0]
    gap = (
        ranked[1]["cost"] - best["cost"]
        if len(ranked) > 1 else None)
    return {
        "retract_length_mm": best["retract_length_mm"],
        "experimental": True,
        "cost": best["cost"],
        "cost_gap_to_second_best": gap,
        "apply_automatically": False,
    }


def analyze_retract_dataset(dataset_dir):
    rows = _load_combined(os.path.join(dataset_dir, "combined.csv"))
    events = _load_events(os.path.join(dataset_dir, "events.csv"))
    quality_path = os.path.join(dataset_dir, "quality.json")
    quality = None
    if os.path.exists(quality_path):
        with open(quality_path) as handle:
            quality = json.load(handle)
    quality_gate_passed = bool(
        quality and quality.get("analysis_eligible", False))

    retract_events = [
        event for event in events if event["event"] == "retract_start"]
    cycles_by_value = {}
    for event in retract_events:
        try:
            r_text, cycle_text = event["value"].split(":", 1)
            r_value = float(r_text)
            cycle_index = int(cycle_text)
        except (TypeError, ValueError):
            continue
        following = [
            candidate for candidate in events
            if candidate["sequence"] > event["sequence"]
            and candidate["event"] in ("unretract_start", "cycle_end",
                                       "r_end", "retract_sweep_end")
        ]
        if (len(following) < 2
                or following[0]["event"] != "unretract_start"
                or following[1]["event"] not in (
                    "cycle_end", "r_end", "retract_sweep_end")):
            continue
        metrics = cycle_metrics(
            rows, event["print_time"], following[0]["print_time"],
            following[1]["print_time"])
        metrics["cycle"] = cycle_index
        metrics["retract_print_time"] = event["print_time"]
        metrics["unretract_print_time"] = following[0]["print_time"]
        cycles_by_value.setdefault(r_value, []).append(metrics)

    per_value = []
    for r_value in sorted(cycles_by_value):
        aggregate = _aggregate(cycles_by_value[r_value])
        aggregate["retract_length_mm"] = r_value
        aggregate["cycles"] = cycles_by_value[r_value]
        per_value.append(aggregate)

    recommendation = _rank_retract_lengths(per_value, quality_gate_passed)
    result = {
        "format_version": 1,
        "dataset": os.path.basename(os.path.abspath(dataset_dir)),
        "combined_samples": len(rows),
        "marker_count": len(events),
        "retract_cycle_count": len(retract_events),
        "per_value": per_value,
        "recommendation": recommendation,
        "quality_gate_passed": quality_gate_passed,
        "printer_action": "none",
        "notes": [
            "Experimental residual-pressure estimator for firmware "
            "retraction lengths.",
            "The analysis itself never applies anything; the bounded sweep "
            "runner may apply a recommendation at runtime only, within the "
            "configured deviation limit, and never persists it.",
            "LIS2DW motion RMS is diagnostic and is not part of the cost.",
            "Missing or implausible data suppresses the recommendation but "
            "never pauses or cancels a print.",
        ],
    }
    output_path = os.path.join(dataset_dir, "retract_analysis.json")
    with open(output_path, "w") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a marked AutoPA retraction sweep dataset")
    parser.add_argument("dataset_dir")
    args = parser.parse_args()
    result = analyze_retract_dataset(args.dataset_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
