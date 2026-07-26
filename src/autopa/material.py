"""Filament consistency checks and sensor-derived temperature comparison."""
import argparse
import csv
import json
import os
import statistics


def _median(values):
    return statistics.median(values) if values else None


def _temperature_summary(dataset_dir):
    path = os.path.join(dataset_dir, "printer_status.csv")
    if not os.path.exists(path):
        return None
    temperatures = []
    targets = []
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("extruder_temperature_c"):
                temperatures.append(float(row["extruder_temperature_c"]))
            if row.get("extruder_target_c"):
                targets.append(float(row["extruder_target_c"]))
    if not temperatures:
        return None
    target = _median([value for value in targets if value > 0])
    median_temperature = _median(temperatures)
    return {
        "median_temperature_c": median_temperature,
        "minimum_temperature_c": min(temperatures),
        "maximum_temperature_c": max(temperatures),
        "peak_to_peak_c": max(temperatures) - min(temperatures),
        "median_target_c": target,
        "target_error_c": (
            None if target is None else median_temperature - target),
        "samples": len(temperatures),
    }


def inspect_material(dataset_dir):
    quality_path = os.path.join(dataset_dir, "quality.json")
    analysis_path = os.path.join(dataset_dir, "analysis.json")
    filament_path = os.path.join(
        dataset_dir, "filament_diagnostics.json")
    reasons = []
    if not os.path.exists(quality_path):
        reasons.append("quality_missing")
        quality = {}
    else:
        with open(quality_path) as handle:
            quality = json.load(handle)
        if not quality.get("analysis_eligible", False):
            reasons.append("quality_gate_failed")
    if not os.path.exists(analysis_path):
        reasons.append("pa_analysis_missing")
        analysis = {}
    else:
        with open(analysis_path) as handle:
            analysis = json.load(handle)
    filament = {}
    if os.path.exists(filament_path):
        with open(filament_path) as handle:
            filament = json.load(handle)
        if filament.get("events"):
            reasons.append("lost_extrusion_pressure_detected")

    recommendation = analysis.get("recommendation")
    selected = None
    if recommendation is None:
        reasons.append("pa_recommendation_missing")
    else:
        selected = next(
            (result for result in analysis.get("per_k", [])
             if result.get("k") == recommendation.get("pressure_advance")),
            None)
        if selected is None:
            reasons.append("recommended_pa_metrics_missing")

    metrics = {}
    if selected is not None:
        medians = selected.get("medians", {})
        mads = selected.get("mads", {})
        amplitude = medians.get("amplitude")
        amplitude_mad = mads.get("amplitude")
        snr = medians.get("signal_to_noise_mad")
        amplitude_cv = (
            None if not amplitude or amplitude_mad is None
            else abs(amplitude_mad / amplitude))
        metrics = {
            "pressure_advance": selected.get("k"),
            "pa_cost": selected.get("cost"),
            "cycles_total": selected.get("cycles_total"),
            "cycles_included": selected.get("cycles_included"),
            "amplitude": amplitude,
            "amplitude_mad": amplitude_mad,
            "amplitude_mad_fraction": amplitude_cv,
            "signal_to_noise_mad": snr,
        }
        if selected.get("cycles_included", 0) < 3:
            reasons.append("fewer_than_3_valid_cycles")
        if amplitude_cv is not None and amplitude_cv > 0.25:
            reasons.append("pressure_cycle_variation_above_25_percent")
        if snr is not None and snr < 6.0:
            reasons.append("pressure_signal_to_noise_below_6")

    temperature = _temperature_summary(dataset_dir)
    if temperature is None:
        reasons.append("temperature_telemetry_missing")
    else:
        if temperature["peak_to_peak_c"] > 3.0:
            reasons.append("temperature_span_above_3c")
        target_error = temperature.get("target_error_c")
        if target_error is not None and abs(target_error) > 2.0:
            reasons.append("temperature_more_than_2c_from_target")

    hard_reasons = {
        "quality_missing", "quality_gate_failed", "pa_analysis_missing",
        "pa_recommendation_missing", "recommended_pa_metrics_missing",
        "fewer_than_3_valid_cycles", "temperature_telemetry_missing",
        "temperature_span_above_3c",
        "temperature_more_than_2c_from_target",
    }
    status = (
        "unavailable" if any(reason in hard_reasons for reason in reasons)
        else "warning" if reasons else "consistent")
    result = {
        "format_version": 1,
        "dataset": os.path.basename(os.path.abspath(dataset_dir)),
        "status": status,
        "reasons": reasons,
        "temperature": temperature,
        "metrics": metrics,
        "pressure_loss_events": len(filament.get("events", [])),
        "printer_action": "none",
        "limitations": [
            "The load cell cannot directly identify moisture, polymer type, "
            "stringing, thermal degradation or layer adhesion.",
            "A consistent sensor result is not a substitute for a printed "
            "mechanical and visual test.",
        ],
    }
    output_path = os.path.join(dataset_dir, "material_check.json")
    with open(output_path, "w") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result


def _normalize(values):
    low, high = min(values), max(values)
    if high == low:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def compare_material_temperatures(results):
    candidates = [
        result for result in results
        if result.get("status") in ("consistent", "warning")
        and result.get("temperature")
        and result.get("metrics", {}).get("pa_cost") is not None
        and result.get("metrics", {}).get(
            "amplitude_mad_fraction") is not None
        and result.get("metrics", {}).get(
            "signal_to_noise_mad") not in (None, 0)
        and not result.get("pressure_loss_events")
    ]
    temperatures = sorted(set(
        round(result["temperature"]["median_temperature_c"], 3)
        for result in candidates))
    if len(candidates) < 3 or len(temperatures) < 3:
        return {
            "available": False,
            "reason": "at_least_3_valid_distinct_temperatures_required",
            "results": results,
            "printer_action": "none",
        }
    costs = [result["metrics"]["pa_cost"] for result in candidates]
    variations = [
        result["metrics"]["amplitude_mad_fraction"]
        for result in candidates]
    inverse_snrs = [
        1.0 / result["metrics"]["signal_to_noise_mad"]
        for result in candidates]
    normalized_cost = _normalize(costs)
    normalized_variation = _normalize(variations)
    normalized_inverse_snr = _normalize(inverse_snrs)
    ranked = []
    for result, cost_score, variation_score, snr_score in zip(
            candidates, normalized_cost,
            normalized_variation, normalized_inverse_snr):
        score = (
            0.50 * cost_score
            + 0.35 * variation_score
            + 0.15 * snr_score)
        ranked.append({
            "dataset": result["dataset"],
            "temperature_c":
                result["temperature"]["median_temperature_c"],
            "pressure_advance":
                result["metrics"]["pressure_advance"],
            "pa_cost": result["metrics"]["pa_cost"],
            "pressure_variation":
                result["metrics"]["amplitude_mad_fraction"],
            "signal_to_noise_mad":
                result["metrics"]["signal_to_noise_mad"],
            "sensor_score": score,
        })
    ranked.sort(key=lambda item: item["sensor_score"])
    best = ranked[0]
    at_boundary = (
        round(best["temperature_c"], 3) in
        (min(temperatures), max(temperatures)))
    return {
        "available": True,
        "best_tested_temperature_c": best["temperature_c"],
        "recommended_temperature_c": (
            None if at_boundary else best["temperature_c"]),
        "recommended_pressure_advance": (
            None if at_boundary else best["pressure_advance"]),
        "boundary_result_requires_wider_test_range": at_boundary,
        "ranking": ranked,
        "pa_by_temperature": [
            {
                "temperature_c": item["temperature_c"],
                "pressure_advance": item["pressure_advance"],
            }
            for item in sorted(ranked, key=lambda value: value["temperature_c"])
        ],
        "experimental": True,
        "interpretation": "sensor-derived process window",
        "printer_action": "none",
        "limitations": [
            "This ranking does not measure stringing, thermal degradation, "
            "surface quality or layer adhesion.",
            "Validate the selected temperature with a printed test.",
        ],
    }


def compare_dataset_paths(dataset_dirs, output_path=None):
    results = [inspect_material(path) for path in dataset_dirs]
    comparison = compare_material_temperatures(results)
    if output_path:
        with open(output_path, "w") as handle:
            json.dump(comparison, handle, indent=2, sort_keys=True)
            handle.write("\n")
    return comparison


def main():
    parser = argparse.ArgumentParser(
        description="Check filament consistency or compare temperatures")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("dataset_dir")
    compare = subparsers.add_parser("compare-temperatures")
    compare.add_argument("dataset_dirs", nargs="+")
    compare.add_argument("--output")
    args = parser.parse_args()
    if args.command == "check":
        result = inspect_material(args.dataset_dir)
    else:
        result = compare_dataset_paths(
            args.dataset_dirs, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
