"""Align factory-firmware ALPS samples with Klipper accelerometer samples."""
import argparse
import bisect
import csv
import json
import math
import os

from .calibration import counts_to_grams, load_calibration


def linear_fit(points):
    if len(points) < 2:
        raise ValueError("At least two clock synchronization points required")
    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    covariance = sum(
        (x - mean_x) * (y - mean_y) for x, y in points)
    variance = sum((x - mean_x) ** 2 for x, _ in points)
    if variance == 0:
        raise ValueError("Clock synchronization points have no time span")
    slope = covariance / variance
    offset = mean_y - slope * mean_x
    residuals = [y - (slope * x + offset) for x, y in points]
    rms = math.sqrt(sum(value * value for value in residuals) / len(points))
    return slope, offset, rms, max(abs(value) for value in residuals)


def regularize_sample_times(arrival_times):
    if len(arrival_times) < 2:
        raise ValueError("At least two force samples required")
    points = list(enumerate(arrival_times))
    sample_period, start_time, rms, maximum = linear_fit(points)
    if sample_period <= 0:
        raise ValueError("Force sample period must be positive")
    regularized = [
        start_time + index * sample_period
        for index in range(len(arrival_times))
    ]
    return regularized, {
        "force_timestamp_model": "sample_index_linear_fit",
        "force_sample_period_us": sample_period * 1e6,
        "force_sample_rate_model_hz": 1.0 / sample_period,
        "force_arrival_rms_residual_ms": rms * 1000.0,
        "force_arrival_max_residual_ms": maximum * 1000.0,
    }


def interpolate(times, values, target):
    index = bisect.bisect_left(times, target)
    if index == 0 or index >= len(times):
        return None
    left_time, right_time = times[index - 1], times[index]
    left_value, right_value = values[index - 1], values[index]
    if left_value is None or right_value is None:
        return None
    if right_time == left_time:
        return left_value
    fraction = (target - left_time) / (right_time - left_time)
    return left_value + fraction * (right_value - left_value)


def _optional_float(value):
    return None if value is None or value == "" else float(value)


def extruder_state_at(segments, print_time, start_index=0):
    index = start_index
    while index < len(segments):
        segment = segments[index]
        start = segment["print_time"]
        stop = start + segment["duration_s"]
        if print_time < start:
            return 0.0, False, index
        if print_time <= stop:
            elapsed = max(0.0, print_time - start)
            velocity = (
                segment["start_velocity_mm_s"]
                + segment["acceleration_mm_s2"] * elapsed)
            velocity *= segment["direction"]
            return velocity, segment["pressure_advance_active"], index
        index += 1
    return 0.0, False, index


def _load_extruder_segments(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as handle:
        return [
            {
                "print_time": float(row["print_time"]),
                "duration_s": float(row["duration_s"]),
                "start_velocity_mm_s":
                    float(row["start_velocity_mm_s"]),
                "acceleration_mm_s2":
                    float(row["acceleration_mm_s2"]),
                "direction": float(row["direction"]),
                "pressure_advance_active":
                    bool(int(float(row["pressure_advance_active"]))),
            }
            for row in csv.DictReader(handle)
        ]


def align_dataset(dataset_dir, calibration_path=None):
    clock_path = os.path.join(dataset_dir, "clock_sync.csv")
    force_path = os.path.join(dataset_dir, "force.csv")
    acceleration_path = os.path.join(dataset_dir, "acceleration.csv")
    extruder_path = os.path.join(dataset_dir, "extruder_motion.csv")
    with open(clock_path, newline="") as handle:
        clock_rows = list(csv.DictReader(handle))
    clock_points = [
        (float(row["klipper_host_monotonic"]), float(row["print_time"]))
        for row in clock_rows
    ]
    slope, offset, rms, maximum = linear_fit(clock_points)

    with open(force_path, newline="") as handle:
        force_rows = list(csv.DictReader(handle))
    force_arrival_times = [
        int(row["host_monotonic_ns"]) / 1e9 for row in force_rows]
    regularized_force_host_times, force_timing_model = (
        regularize_sample_times(force_arrival_times))
    force_times = [
        slope * host_time + offset
        for host_time in regularized_force_host_times
    ]
    force_raw = [_optional_float(row["raw"]) for row in force_rows]
    force_filtered = [
        _optional_float(row["filtered"]) for row in force_rows]
    calibration = (
        load_calibration(calibration_path) if calibration_path else None)
    extruder_segments = _load_extruder_segments(extruder_path)
    with open(acceleration_path, newline="") as input_handle:
        acceleration_rows = list(csv.DictReader(input_handle))

    output_path = os.path.join(dataset_dir, "combined.csv")
    rows_written = 0
    with open(output_path, "w", newline="") as output_handle:
        fieldnames = [
            "print_time", "force_raw", "force_filtered",
            "force_raw_grams", "force_filtered_grams",
            "commanded_e_velocity_mm_s", "pressure_advance_active",
            "x_mm_s2", "y_mm_s2", "z_mm_s2",
        ]
        writer = csv.DictWriter(output_handle, fieldnames=fieldnames)
        writer.writeheader()
        extruder_index = 0
        if acceleration_rows:
            aligned_rows = (
                (
                    float(row["print_time"]),
                    interpolate(
                        force_times, force_raw, float(row["print_time"])),
                    interpolate(
                        force_times, force_filtered,
                        float(row["print_time"])),
                    row["x_mm_s2"], row["y_mm_s2"], row["z_mm_s2"],
                )
                for row in acceleration_rows
            )
        else:
            aligned_rows = (
                (print_time, raw, filtered, "", "", "")
                for print_time, raw, filtered in zip(
                    force_times, force_raw, force_filtered)
            )
        for print_time, raw, filtered, accel_x, accel_y, accel_z in (
                aligned_rows):
            e_velocity, pa_active, extruder_index = extruder_state_at(
                extruder_segments, print_time, extruder_index)
            if raw is None and filtered is None:
                continue
            writer.writerow({
                "print_time": "%.9f" % print_time,
                "force_raw": "" if raw is None else "%.6f" % raw,
                "force_filtered":
                    "" if filtered is None else "%.6f" % filtered,
                "force_raw_grams": (
                    "" if calibration is None or raw is None
                    else "%.9f" % counts_to_grams(raw, calibration)),
                "force_filtered_grams": (
                    "" if calibration is None or filtered is None
                    else "%.9f" % counts_to_grams(filtered, calibration)),
                "commanded_e_velocity_mm_s": (
                    "%.9f" % e_velocity if extruder_segments else ""),
                "pressure_advance_active": (
                    "1" if pa_active else "0"
                    if extruder_segments else ""),
                "x_mm_s2": accel_x,
                "y_mm_s2": accel_y,
                "z_mm_s2": accel_z,
            })
            rows_written += 1

    diagnostics = {
        "clock_points": len(clock_points),
        "clock_slope": slope,
        "clock_offset": offset,
        "clock_rms_residual_ms": rms * 1000.0,
        "clock_max_residual_ms": maximum * 1000.0,
        "force_samples": len(force_rows),
        "acceleration_samples": len(acceleration_rows),
        "acceleration_available": bool(acceleration_rows),
        "combined_samples": rows_written,
        "calibration_id": (
            calibration["calibration_id"] if calibration else None),
        "force_unit": "grams" if calibration else "counts",
        "extruder_motion_segments": len(extruder_segments),
        **force_timing_model,
    }
    diagnostics_path = os.path.join(dataset_dir, "alignment.json")
    with open(diagnostics_path, "w") as handle:
        json.dump(diagnostics, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return diagnostics


def main():
    parser = argparse.ArgumentParser(
        description="Align an AutoPA ALPS/LIS2DW dataset")
    parser.add_argument("dataset_dir")
    parser.add_argument("--calibration")
    args = parser.parse_args()
    print(json.dumps(
        align_dataset(args.dataset_dir, args.calibration),
        indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
