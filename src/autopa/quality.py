"""Compute acquisition and idle-baseline quality metrics for a dataset."""
import argparse
import csv
import json
import math
import os
import statistics

from .calibration import counts_to_grams, load_calibration


def _read_float_column(path, column):
    with open(path, newline="") as handle:
        return [
            float(row[column]) for row in csv.DictReader(handle)
            if row.get(column) not in (None, "")
        ]


def _series_stats(values):
    if not values:
        return {"samples": 0}
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    return {
        "samples": len(values),
        "mean": statistics.fmean(values),
        "median": median,
        "standard_deviation":
            statistics.pstdev(values) if len(values) > 1 else 0.0,
        "mad": statistics.median(deviations),
        "minimum": min(values),
        "maximum": max(values),
        "peak_to_peak": max(values) - min(values),
    }


def _sample_rate(times):
    if len(times) < 2 or times[-1] <= times[0]:
        return None
    return (len(times) - 1) / (times[-1] - times[0])


def _gap_stats(times, minimum_warning_gap_s):
    intervals = [
        right - left for left, right in zip(times, times[1:])
        if right > left
    ]
    if not intervals:
        return {"samples": len(times), "intervals": 0}
    median_interval = statistics.median(intervals)
    warning_gap = max(10.0 * median_interval, minimum_warning_gap_s)
    gaps = [value for value in intervals if value > warning_gap]
    ordered = sorted(intervals)
    p99_index = min(
        len(ordered) - 1, int(math.ceil(0.99 * len(ordered))) - 1)
    return {
        "samples": len(times),
        "intervals": len(intervals),
        "median_interval_ms": median_interval * 1000.0,
        "p99_interval_ms": ordered[p99_index] * 1000.0,
        "maximum_interval_ms": max(intervals) * 1000.0,
        "warning_threshold_ms": warning_gap * 1000.0,
        "gaps_above_threshold": len(gaps),
    }


def assess_dataset(dataset_dir, calibration_path=None):
    force_path = os.path.join(dataset_dir, "force.csv")
    acceleration_path = os.path.join(dataset_dir, "acceleration.csv")
    manifest_path = os.path.join(dataset_dir, "manifest.json")
    alignment_path = os.path.join(dataset_dir, "alignment.json")

    force_times_ns = _read_float_column(force_path, "host_monotonic_ns")
    raw = _read_float_column(force_path, "raw")
    filtered = _read_float_column(force_path, "filtered")
    acceleration_times = _read_float_column(
        acceleration_path, "print_time")
    axes = {
        "x": _read_float_column(acceleration_path, "x_mm_s2"),
        "y": _read_float_column(acceleration_path, "y_mm_s2"),
        "z": _read_float_column(acceleration_path, "z_mm_s2"),
    }
    with open(manifest_path) as handle:
        manifest = json.load(handle)
    accelerometer_enabled = manifest.get(
        "accelerometer_enabled", manifest.get("accelerometer") is not None)
    alignment = None
    if os.path.exists(alignment_path):
        with open(alignment_path) as handle:
            alignment = json.load(handle)

    axis_stats = {name: _series_stats(values)
                  for name, values in axes.items()}
    means = [
        axis_stats[name].get("mean", 0.0) for name in ("x", "y", "z")]
    gravity_magnitude = (
        math.sqrt(sum(value * value for value in means))
        if acceleration_times else None)
    force_times = [value / 1e9 for value in force_times_ns]
    # USB bulk batching legitimately stalls a kHz stream for 10-20 ms and
    # then delivers a burst; only stalls beyond 25 ms indicate real loss.
    force_gaps = _gap_stats(force_times, 0.025)
    acceleration_gaps = _gap_stats(acceleration_times, 0.030)
    force_rate = _sample_rate(force_times)
    acceleration_rate = _sample_rate(acceleration_times)
    warnings = []
    errors = manifest.get("errors", [])
    capture_stats = manifest.get("stats", {})
    if errors:
        warnings.append("capture_manifest_contains_errors")
    if (accelerometer_enabled
            and capture_stats.get("acceleration_errors", 0)):
        warnings.append("accelerometer_errors_nonzero")
    if (accelerometer_enabled
            and capture_stats.get("acceleration_overflows", 0)):
        warnings.append("accelerometer_overflows_nonzero")
    if alignment is None:
        warnings.append("alignment_missing")
    elif alignment.get("clock_max_residual_ms", float("inf")) > 1.0:
        warnings.append("clock_alignment_residual_above_1ms")
    # The align step replaces USB arrival times with a uniform
    # sample-index grid, so arrival burstiness (USB bulk batching easily
    # produces 10-20 ms bursts at kHz rates) does not distort the
    # reconstructed print_time at all. Only a severely broken transport is
    # still diagnostic; 25 ms RMS is far above normal batching.
    force_arrival_rms_residual_ms = (
        alignment.get("force_arrival_rms_residual_ms")
        if alignment is not None else None
    )
    if (
        force_arrival_rms_residual_ms is not None
        and force_arrival_rms_residual_ms > 25.0
    ):
        warnings.append("force_arrival_rms_residual_above_25ms")
    if alignment is not None and alignment.get("clock_points", 0) < 3:
        warnings.append("fewer_than_3_clock_sync_points")
    if not raw or not filtered:
        warnings.append("force_channel_missing")
    if force_rate is None or force_rate < 1000.0:
        warnings.append("force_sample_rate_below_1000hz")
    if (accelerometer_enabled
            and (acceleration_rate is None or acceleration_rate < 100.0)):
        warnings.append("acceleration_sample_rate_below_100hz")
    if force_gaps.get("gaps_above_threshold", 0):
        warnings.append("force_timestamp_gaps")
    if (accelerometer_enabled
            and acceleration_gaps.get("gaps_above_threshold", 0)):
        warnings.append("acceleration_timestamp_gaps")
    if raw and max(abs(value) for value in raw) >= 0.95 * 8388607:
        warnings.append("force_adc_near_signed_24bit_limit")
    if raw and len(set(raw)) == 1:
        warnings.append("force_raw_flatline")
    if filtered and len(set(filtered)) == 1:
        warnings.append("force_filtered_flatline")
    calibration = None
    calibrated_stats = None
    if calibration_path:
        calibration = load_calibration(calibration_path)
        calibrated_stats = {
            "calibration_id": calibration["calibration_id"],
            "raw_grams": _series_stats([
                counts_to_grams(value, calibration) for value in raw]),
            "filtered_grams": _series_stats([
                counts_to_grams(value, calibration) for value in filtered]),
        }

    result = {
        "format_version": 1,
        "dataset": os.path.basename(os.path.abspath(dataset_dir)),
        "alps_firmware": manifest.get("alps_firmware"),
        "force_sample_rate_hz": force_rate,
        "acceleration_sample_rate_hz": acceleration_rate,
        "accelerometer_enabled": accelerometer_enabled,
        "accelerometer_type": manifest.get("accelerometer_type"),
        "force_timing": force_gaps,
        "acceleration_timing": acceleration_gaps,
        "force_raw": _series_stats(raw),
        "force_filtered": _series_stats(filtered),
        "force_calibrated": calibrated_stats,
        "acceleration": axis_stats,
        "mean_acceleration_magnitude_mm_s2": gravity_magnitude,
        "capture_stats": capture_stats,
        "alignment": alignment,
        "warnings": warnings,
        "acquisition_ok": not warnings,
        "analysis_eligible": not warnings,
        "printer_action": "none",
    }
    output_path = os.path.join(dataset_dir, "quality.json")
    with open(output_path, "w") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Assess an AutoPA capture and idle baseline")
    parser.add_argument("dataset_dir")
    parser.add_argument("--calibration")
    args = parser.parse_args()
    print(json.dumps(
        assess_dataset(args.dataset_dir, args.calibration),
        indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
