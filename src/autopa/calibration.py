"""Per-machine force calibration for Mellow factory-firmware ALPS data."""
import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import statistics


STANDARD_GRAVITY = 9.80665


def _force_path(path):
    if os.path.isdir(path):
        path = os.path.join(path, "force.csv")
    if not os.path.isfile(path):
        raise ValueError("Force capture not found: %s" % path)
    return path


def capture_summary(path, channel="filtered"):
    path = _force_path(path)
    with open(path, newline="") as handle:
        values = [
            float(row[channel]) for row in csv.DictReader(handle)
            if row.get(channel) not in (None, "")
        ]
    if len(values) < 100:
        raise ValueError(
            "Calibration capture requires at least 100 %s samples: %s"
            % (channel, path))
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    return {
        "path": path,
        "samples": len(values),
        "median_counts": median,
        "mean_counts": statistics.fmean(values),
        "standard_deviation_counts": statistics.pstdev(values),
        "mad_counts": statistics.median(deviations),
        "minimum_counts": min(values),
        "maximum_counts": max(values),
    }


def _linear_fit(points):
    if len(points) < 2:
        raise ValueError("At least zero and one known load are required")
    mean_x = statistics.fmean(point[0] for point in points)
    mean_y = statistics.fmean(point[1] for point in points)
    variance = sum((x - mean_x) ** 2 for x, _ in points)
    if variance <= 0:
        raise ValueError("Calibration loads need at least two distinct masses")
    slope = sum(
        (x - mean_x) * (y - mean_y) for x, y in points) / variance
    offset = mean_y - slope * mean_x
    residuals = [y - (offset + slope * x) for x, y in points]
    rms = math.sqrt(statistics.fmean(value * value for value in residuals))
    maximum = max(abs(value) for value in residuals)
    total = sum((y - mean_y) ** 2 for _, y in points)
    residual_sum = sum(value * value for value in residuals)
    r_squared = 1.0 if total == 0 else 1.0 - residual_sum / total
    return slope, offset, rms, maximum, r_squared


def build_calibration(zero_path, load_points, channel="filtered",
                      label=None, temperature_c=None):
    if not load_points:
        raise ValueError("At least one known load capture is required")
    summaries = [(0.0, capture_summary(zero_path, channel))]
    seen_masses = {0.0}
    for grams, path in load_points:
        grams = float(grams)
        if grams <= 0:
            raise ValueError("Known calibration loads must be positive")
        if grams in seen_masses:
            raise ValueError("Duplicate calibration load: %s grams" % grams)
        seen_masses.add(grams)
        summaries.append((grams, capture_summary(path, channel)))
    summaries.sort(key=lambda item: item[0])
    points = [
        (grams, summary["median_counts"])
        for grams, summary in summaries
    ]
    scale, offset, rms, maximum, r_squared = _linear_fit(points)
    if scale == 0:
        raise ValueError("Calibration produced a zero scale")
    count_span = (
        max(summary["median_counts"] for _, summary in summaries)
        - min(summary["median_counts"] for _, summary in summaries))
    noise_mad = max(summary["mad_counts"] for _, summary in summaries)
    noise_std = max(
        summary["standard_deviation_counts"] for _, summary in summaries)
    signal_to_noise_mad = (
        float("inf") if noise_mad == 0 else abs(count_span) / noise_mad)
    if signal_to_noise_mad < 10.0:
        raise ValueError(
            "Calibration load span is below 10x the measured noise MAD")
    grams_per_count = 1.0 / scale
    fit_span_fraction = (
        0.0 if count_span == 0 else maximum / abs(count_span))
    valid = fit_span_fraction <= 0.02 and r_squared >= 0.995
    warnings = []
    if not valid:
        warnings.append("calibration_fit_residual_too_large")
    core = {
        "format_version": 1,
        "channel": channel,
        "label": label,
        "temperature_c": temperature_c,
        "offset_counts": offset,
        "counts_per_gram": scale,
        "grams_per_count": grams_per_count,
        "newtons_per_count": grams_per_count * STANDARD_GRAVITY / 1000.0,
        "polarity": "increasing" if scale > 0 else "decreasing",
        "fit_rms_counts": rms,
        "fit_max_residual_counts": maximum,
        "fit_max_residual_fraction_of_span": fit_span_fraction,
        "fit_r_squared": r_squared,
        "noise_mad_counts": noise_mad,
        "noise_standard_deviation_counts": noise_std,
        "detection_limit_6mad_grams":
            0.0 if noise_mad == 0 else 6.0 * noise_mad / abs(scale),
        "signal_span_to_noise_mad": signal_to_noise_mad,
        "valid": valid,
        "warnings": warnings,
        "points": [
            {
                "grams": grams,
                "median_counts": summary["median_counts"],
                "mad_counts": summary["mad_counts"],
                "standard_deviation_counts":
                    summary["standard_deviation_counts"],
                "samples": summary["samples"],
                "source": os.path.basename(summary["path"]),
            }
            for grams, summary in summaries
        ],
    }
    canonical = json.dumps(
        core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    core["calibration_id"] = hashlib.sha256(canonical).hexdigest()[:16]
    core["created_utc"] = datetime.datetime.now(
        datetime.timezone.utc).isoformat()
    return core


def load_calibration(path):
    with open(path) as handle:
        calibration = json.load(handle)
    required = (
        "offset_counts", "counts_per_gram", "calibration_id", "valid")
    missing = [key for key in required if key not in calibration]
    if missing:
        raise ValueError(
            "Calibration is missing fields: %s" % ", ".join(missing))
    if not calibration["valid"]:
        raise ValueError("Calibration is marked invalid")
    if not calibration["counts_per_gram"]:
        raise ValueError("Calibration scale is zero")
    return calibration


def counts_to_grams(counts, calibration):
    if counts is None:
        return None
    return (
        float(counts) - float(calibration["offset_counts"])
    ) / float(calibration["counts_per_gram"])


def _parse_point(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "Use GRAMS=PATH, for example 100=capture-100g")
    grams, path = value.split("=", 1)
    try:
        grams = float(grams)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Invalid calibration mass: %s" % grams) from exc
    return grams, path


def main():
    parser = argparse.ArgumentParser(
        description="Build a per-machine ALPS force calibration")
    parser.add_argument("--zero", required=True)
    parser.add_argument(
        "--point", action="append", type=_parse_point, required=True,
        help="Known load as GRAMS=CAPTURE_PATH; may be repeated")
    parser.add_argument(
        "--channel", choices=("raw", "filtered"), default="filtered")
    parser.add_argument("--label")
    parser.add_argument("--temperature-c", type=float)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    calibration = build_calibration(
        args.zero, args.point, args.channel,
        args.label, args.temperature_c)
    with open(args.output, "w") as handle:
        json.dump(calibration, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(calibration, indent=2, sort_keys=True))
    if not calibration["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
