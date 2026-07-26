"""Conservative offline detection of lost extrusion pressure."""
import argparse
import csv
import json
import math
import os
import statistics


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    left = int(math.floor(position))
    right = int(math.ceil(position))
    if left == right:
        return ordered[left]
    weight = position - left
    return ordered[left] * (1.0 - weight) + ordered[right] * weight


def _force_value(row):
    for field in (
            "force_filtered_grams", "force_filtered",
            "force_raw_grams", "force_raw"):
        value = row.get(field)
        if value not in (None, ""):
            return float(value), (
                "grams" if field.endswith("_grams") else "counts")
    return None, None


def load_monitor_rows(path):
    rows = []
    unit = None
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            velocity = row.get("commanded_e_velocity_mm_s")
            if velocity in (None, ""):
                continue
            force, row_unit = _force_value(row)
            if force is None:
                continue
            unit = unit or row_unit
            rows.append({
                "print_time": float(row["print_time"]),
                "force": force,
                "e_velocity": float(velocity),
            })
    return rows, unit


def detect_pressure_loss(rows, min_e_velocity=0.5, drop_ratio=0.15,
                         confirm_seconds=1.5, settle_seconds=0.5,
                         max_sample_gap=0.1):
    if len(rows) < 20:
        return {
            "available": False,
            "reason": "insufficient_combined_samples",
            "events": [],
        }
    idle_forces = [
        row["force"] for row in rows
        if abs(row["e_velocity"]) <= 0.02
    ]
    if len(idle_forces) < 20:
        return {
            "available": False,
            "reason": "insufficient_no_flow_baseline",
            "events": [],
        }
    baseline = statistics.median(idle_forces)
    baseline_mad = statistics.median(
        abs(value - baseline) for value in idle_forces)
    candidates = [
        abs(row["force"] - baseline) / row["e_velocity"]
        for row in rows if row["e_velocity"] >= min_e_velocity
    ]
    if len(candidates) < 20:
        return {
            "available": False,
            "reason": "insufficient_positive_extrusion",
            "events": [],
            "baseline": baseline,
            "baseline_mad": baseline_mad,
        }
    reference_per_velocity = _percentile(candidates, 0.75)
    median_velocity = statistics.median(
        row["e_velocity"] for row in rows
        if row["e_velocity"] >= min_e_velocity)
    reference_pressure = reference_per_velocity * median_velocity
    if reference_pressure < max(1e-12, 6.0 * baseline_mad):
        return {
            "available": False,
            "reason": "extrusion_pressure_below_6x_baseline_mad",
            "events": [],
            "baseline": baseline,
            "baseline_mad": baseline_mad,
            "reference_pressure": reference_pressure,
        }

    events = []
    extrusion_started = None
    settling_until = None
    suspicious_started = None
    minimum_ratio = None
    event_active = False
    last_time = None
    last_velocity = None
    for row in rows:
        now = row["print_time"]
        velocity = row["e_velocity"]
        if last_time is not None and now - last_time > max_sample_gap:
            suspicious_started = None
            minimum_ratio = None
            extrusion_started = None
            settling_until = None
        last_time = now
        if velocity < min_e_velocity:
            extrusion_started = None
            settling_until = None
            suspicious_started = None
            minimum_ratio = None
            event_active = False
            last_velocity = velocity
            continue
        if extrusion_started is None:
            extrusion_started = now
            settling_until = now + settle_seconds
        elif (last_velocity is not None and last_velocity >= min_e_velocity
              and abs(velocity - last_velocity)
              > max(0.5, 0.5 * abs(last_velocity))):
            settling_until = now + settle_seconds
            suspicious_started = None
            minimum_ratio = None
        last_velocity = velocity
        pressure_per_velocity = (
            abs(row["force"] - baseline) / velocity)
        ratio = pressure_per_velocity / reference_per_velocity
        if now < settling_until:
            continue
        if ratio < drop_ratio:
            if suspicious_started is None:
                suspicious_started = now
                minimum_ratio = ratio
            else:
                minimum_ratio = min(minimum_ratio, ratio)
            if (not event_active
                    and now - suspicious_started >= confirm_seconds):
                events.append({
                    "event": "lost_extrusion_pressure",
                    "classification":
                        "possible_filament_break_or_empty_feed",
                    "start_print_time": suspicious_started,
                    "confirmed_print_time": now,
                    "duration_to_confirmation_s":
                        now - suspicious_started,
                    "minimum_pressure_ratio": minimum_ratio,
                    "commanded_e_velocity_mm_s": velocity,
                    "confidence": "advisory",
                    "printer_action": "none",
                })
                event_active = True
        else:
            suspicious_started = None
            minimum_ratio = None
            if ratio >= 0.5:
                event_active = False

    return {
        "available": True,
        "reason": None,
        "events": events,
        "baseline": baseline,
        "baseline_mad": baseline_mad,
        "reference_pressure_per_e_velocity": reference_per_velocity,
        "reference_pressure_at_median_velocity": reference_pressure,
        "median_positive_e_velocity_mm_s": median_velocity,
        "parameters": {
            "min_e_velocity_mm_s": min_e_velocity,
            "drop_ratio": drop_ratio,
            "confirm_seconds": confirm_seconds,
            "settle_seconds": settle_seconds,
            "max_sample_gap_seconds": max_sample_gap,
        },
    }


def analyze_filament(dataset_dir, **parameters):
    quality_path = os.path.join(dataset_dir, "quality.json")
    quality_eligible = False
    if os.path.exists(quality_path):
        with open(quality_path) as handle:
            quality_eligible = bool(
                json.load(handle).get("analysis_eligible", False))
    combined_path = os.path.join(dataset_dir, "combined.csv")
    rows, unit = load_monitor_rows(combined_path)
    if not quality_eligible:
        result = {
            "format_version": 1,
            "available": False,
            "reason": "dataset_quality_gate_failed_or_missing",
            "events": [],
            "printer_action": "none",
        }
    else:
        result = detect_pressure_loss(rows, **parameters)
        result.update({
            "format_version": 1,
            "dataset": os.path.basename(os.path.abspath(dataset_dir)),
            "force_unit": unit,
            "printer_action": "none",
        })
    output_path = os.path.join(
        dataset_dir, "filament_diagnostics.json")
    with open(output_path, "w") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Detect advisory loss of extrusion pressure")
    parser.add_argument("dataset_dir")
    parser.add_argument("--min-e-velocity", type=float, default=0.5)
    parser.add_argument("--drop-ratio", type=float, default=0.15)
    parser.add_argument("--confirm-seconds", type=float, default=1.5)
    parser.add_argument("--settle-seconds", type=float, default=0.5)
    parser.add_argument("--max-sample-gap", type=float, default=0.1)
    args = parser.parse_args()
    result = analyze_filament(
        args.dataset_dir,
        min_e_velocity=args.min_e_velocity,
        drop_ratio=args.drop_ratio,
        confirm_seconds=args.confirm_seconds,
        settle_seconds=args.settle_seconds,
        max_sample_gap=args.max_sample_gap)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
