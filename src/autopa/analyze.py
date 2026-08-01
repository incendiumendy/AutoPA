"""Experimental step-response analysis for marked AutoPA sweep datasets."""
import argparse
import csv
import json
import math
import os
import statistics


def _median(values):
    return statistics.median(values) if values else None


def _mad(values):
    if not values:
        return None
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def _window(rows, start, stop, field):
    return [
        row[field] for row in rows
        if start <= row["print_time"] <= stop
    ]


def _mean_square_motion(rows, start, stop):
    selected = [
        row for row in rows
        if start <= row["print_time"] <= stop
        and all(row[field] is not None
                for field in ("x_mm_s2", "y_mm_s2", "z_mm_s2"))]
    if not selected:
        return None
    centers = {
        field: statistics.median(row[field] for row in selected)
        for field in ("x_mm_s2", "y_mm_s2", "z_mm_s2")
    }
    squares = [
        sum((row[field] - centers[field]) ** 2
            for field in centers)
        for row in selected
    ]
    return math.sqrt(statistics.fmean(squares))


def _trapezoid_area(rows, start, stop, transform):
    selected = [
        row for row in rows if start <= row["print_time"] <= stop]
    area = 0.0
    for left, right in zip(selected, selected[1:]):
        dt = right["print_time"] - left["print_time"]
        area += 0.5 * dt * (
            transform(left["force"]) + transform(right["force"]))
    return area


def cycle_metrics(rows, rise, fall, next_rise=None):
    """Return direction-normalized metrics for one slow-fast-slow cycle."""
    pre = _window(rows, rise - 0.25, rise - 0.05, "force")
    high = _window(rows, rise + 0.10, fall - 0.03, "force")
    low_stop = fall + 0.40
    if next_rise is not None:
        low_stop = min(low_stop, next_rise - 0.05)
    post = _window(rows, fall + 0.10, low_stop, "force")
    if min(len(pre), len(high), len(post)) < 4:
        return None
    low_before = _median(pre)
    high_level = _median(high)
    low_after = _median(post)
    baseline = 0.5 * (low_before + low_after)
    signed_amplitude = high_level - baseline
    noise_mad = _mad(pre + post)
    if signed_amplitude == 0:
        return {
            "included": False,
            "reason": "no_step_amplitude",
            "amplitude": 0.0,
            "baseline_mad": noise_mad,
        }
    direction = 1.0 if signed_amplitude > 0 else -1.0
    amplitude = abs(signed_amplitude)
    if noise_mad is not None and amplitude < max(1.0, 3.0 * noise_mad):
        return {
            "included": False,
            "reason": "step_amplitude_below_3x_baseline_mad",
            "amplitude": amplitude,
            "baseline_mad": noise_mad,
        }

    oriented = lambda value: direction * (value - baseline)
    rise_values = _window(rows, rise, fall, "force")
    fall_values = _window(rows, fall, low_stop, "force")
    overshoot = max(
        0.0, max(oriented(value) for value in rise_values) - amplitude)
    undershoot = max(
        0.0, -min(oriented(value) for value in fall_values))
    rise_error_area = _trapezoid_area(
        rows, rise, fall,
        lambda value: abs(amplitude - oriented(value))) / amplitude
    fall_error_area = _trapezoid_area(
        rows, fall, low_stop,
        lambda value: abs(oriented(value))) / amplitude
    return {
        "included": True,
        "amplitude": amplitude,
        "baseline_mad": noise_mad,
        "signal_to_noise_mad":
            None if not noise_mad else amplitude / noise_mad,
        "overshoot_ratio": overshoot / amplitude,
        "undershoot_ratio": undershoot / amplitude,
        "rise_error_area_s": rise_error_area,
        "fall_error_area_s": fall_error_area,
        "motion_rms_mm_s2": _mean_square_motion(
            rows, rise - 0.05, low_stop),
    }


def _load_combined(path):
    rows = []
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            force = (
                row.get("force_filtered_grams")
                or row.get("force_filtered")
                or row.get("force_raw_grams")
                or row.get("force_raw"))
            if not force:
                continue
            rows.append({
                "print_time": float(row["print_time"]),
                "force": float(force),
                "x_mm_s2": (
                    float(row["x_mm_s2"]) if row.get("x_mm_s2") else None),
                "y_mm_s2": (
                    float(row["y_mm_s2"]) if row.get("y_mm_s2") else None),
                "z_mm_s2": (
                    float(row["z_mm_s2"]) if row.get("z_mm_s2") else None),
            })
    return rows


def _load_events(path):
    events = []
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            if not row.get("print_time"):
                continue
            events.append({
                "sequence": int(row["sequence"]),
                "print_time": float(row["print_time"]),
                "event": row["event"],
                "value": row.get("value", ""),
            })
    return sorted(events, key=lambda item: item["sequence"])


def _aggregate(cycles):
    metric_names = (
        "amplitude", "baseline_mad", "signal_to_noise_mad",
        "overshoot_ratio", "undershoot_ratio",
        "rise_error_area_s", "fall_error_area_s",
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


def _rank_pressure_advance(per_k, allow_recommendation):
    cost_metrics = (
        "overshoot_ratio", "undershoot_ratio",
        "rise_error_area_s", "fall_error_area_s")
    eligible = [
        result for result in per_k if result["cycles_included"] >= 3]
    for result in per_k:
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
        "pressure_advance": best["k"],
        "experimental": True,
        "cost": best["cost"],
        "cost_gap_to_second_best": gap,
        "apply_automatically": False,
    }


def analyze_dataset(dataset_dir):
    rows = _load_combined(os.path.join(dataset_dir, "combined.csv"))
    events = _load_events(os.path.join(dataset_dir, "events.csv"))
    quality_path = os.path.join(dataset_dir, "quality.json")
    quality = None
    if os.path.exists(quality_path):
        with open(quality_path) as handle:
            quality = json.load(handle)
    quality_gate_passed = bool(
        quality and quality.get("analysis_eligible", False))
    fast_events = [
        event for event in events if event["event"] == "fast_start"]
    cycles_by_k = {}
    for index, event in enumerate(fast_events):
        try:
            k_text, cycle_text = event["value"].split(":", 1)
            k_value = float(k_text)
            cycle_index = int(cycle_text)
        except (TypeError, ValueError):
            continue
        following = [
            candidate for candidate in events
            if candidate["sequence"] > event["sequence"]
            and candidate["event"] in ("slow_start", "k_end")
        ]
        if not following:
            continue
        fall = following[0]["print_time"]
        next_rise = (
            fast_events[index + 1]["print_time"]
            if index + 1 < len(fast_events) else None)
        metrics = cycle_metrics(
            rows, event["print_time"], fall, next_rise)
        if metrics is None:
            metrics = {"included": False, "reason": "insufficient_samples"}
        metrics["cycle"] = cycle_index
        metrics["rise_print_time"] = event["print_time"]
        metrics["fall_print_time"] = fall
        cycles_by_k.setdefault(k_value, []).append(metrics)

    per_k = []
    for k_value in sorted(cycles_by_k):
        aggregate = _aggregate(cycles_by_k[k_value])
        aggregate["k"] = k_value
        aggregate["cycles"] = cycles_by_k[k_value]
        per_k.append(aggregate)

    recommendation = _rank_pressure_advance(
        per_k, quality_gate_passed)
    result = {
        "format_version": 1,
        "dataset": os.path.basename(os.path.abspath(dataset_dir)),
        "combined_samples": len(rows),
        "marker_count": len(events),
        "fast_transition_count": len(fast_events),
        "per_k": per_k,
        "recommendation": recommendation,
        "quality_gate_passed": quality_gate_passed,
        "printer_action": "none",
        "notes": [
            "Experimental step-response estimator.",
            "The analysis itself never applies anything; the bounded sweep "
            "runner may apply a recommendation at runtime only, within the "
            "configured deviation limit, and never persists it.",
            "LIS2DW motion RMS is diagnostic and is not part of the PA cost.",
            "Missing or implausible data suppresses the recommendation but "
            "never pauses or cancels a print.",
        ],
    }
    output_path = os.path.join(dataset_dir, "analysis.json")
    with open(output_path, "w") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result


def analyze_combined_datasets(dataset_dirs, output_path=None):
    analyses = [analyze_dataset(path) for path in dataset_dirs]
    accepted = [
        result for result in analyses if result["quality_gate_passed"]]
    cycles_by_k = {}
    for result in accepted:
        for item in result["per_k"]:
            for cycle in item["cycles"]:
                copied = dict(cycle)
                copied["source_dataset"] = result["dataset"]
                cycles_by_k.setdefault(item["k"], []).append(copied)
    per_k = []
    for k_value in sorted(cycles_by_k):
        aggregate = _aggregate(cycles_by_k[k_value])
        aggregate["k"] = k_value
        aggregate["cycles"] = cycles_by_k[k_value]
        per_k.append(aggregate)
    recommendation = _rank_pressure_advance(
        per_k, bool(accepted))
    result = {
        "format_version": 1,
        "mode": "combined_quality_gated_runs",
        "source_datasets": [
            analysis["dataset"] for analysis in analyses],
        "accepted_datasets": [
            analysis["dataset"] for analysis in accepted],
        "rejected_datasets": [
            analysis["dataset"] for analysis in analyses
            if not analysis["quality_gate_passed"]],
        "per_k": per_k,
        "recommendation": recommendation,
        "quality_gate_passed": bool(accepted),
        "printer_action": "none",
        "notes": [
            "Only cycles from quality-gated datasets are pooled.",
            "At least three included cycles are required per PA value.",
            "The result remains experimental; any runtime apply happens only "
            "through the bounded sweep runner within its deviation limit.",
        ],
    }
    if output_path:
        with open(output_path, "w") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a marked AutoPA sweep dataset")
    parser.add_argument("dataset_dirs", nargs="+")
    parser.add_argument(
        "--output", help="Optional output path for a combined analysis")
    args = parser.parse_args()
    result = (
        analyze_dataset(args.dataset_dirs[0])
        if len(args.dataset_dirs) == 1
        else analyze_combined_datasets(args.dataset_dirs, args.output))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
