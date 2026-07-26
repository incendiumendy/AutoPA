"""Generate separate, temperature-validated AutoPA sweep files."""
import argparse
import json
import os

from .sweep import build_sweep, decimal_range


def parse_temperatures(value):
    try:
        temperatures = [float(item.strip()) for item in value.split(",")]
    except ValueError as exc:
        raise ValueError("Temperatures must be comma-separated numbers") from exc
    if len(temperatures) < 3:
        raise ValueError("At least three temperatures are required")
    if len(set(temperatures)) != len(temperatures):
        raise ValueError("Temperatures must be distinct")
    if any(value <= 0 or value > 500 for value in temperatures):
        raise ValueError("Temperatures must be between 0 and 500C")
    return sorted(temperatures)


def build_temperature_plan(output_dir, temperatures, k_values, cycles,
                           restore_advance, tolerance=2.0,
                           material_label=None):
    os.makedirs(output_dir, exist_ok=True)
    files = []
    total_filament = 0.0
    total_duration = 0.0
    for temperature in temperatures:
        filename = "autopa_%gC.gcode" % temperature
        gcode_path = os.path.join(output_dir, filename)
        gcode, plan = build_sweep(
            k_values, cycles, restore_advance=restore_advance,
            target_temperature=temperature,
            temperature_tolerance=tolerance)
        plan["material_label"] = material_label
        with open(gcode_path, "w") as handle:
            handle.write(gcode)
        plan_path = os.path.splitext(gcode_path)[0] + ".json"
        with open(plan_path, "w") as handle:
            json.dump(plan, handle, indent=2, sort_keys=True)
            handle.write("\n")
        files.append({
            "temperature_c": temperature,
            "gcode": os.path.basename(gcode_path),
            "plan": os.path.basename(plan_path),
            "filament_length_mm": plan["filament_length_mm"],
            "estimated_sweep_duration_s":
                plan["estimated_sweep_duration_s"],
        })
        total_filament += plan["filament_length_mm"]
        total_duration += plan["estimated_sweep_duration_s"]
    result = {
        "format_version": 1,
        "material_label": material_label,
        "temperatures_c": temperatures,
        "restore_advance": restore_advance,
        "files": files,
        "total_filament_length_mm": total_filament,
        "total_estimated_sweep_duration_s": total_duration,
        "heating_is_not_automated": True,
        "printer_action": "none",
    }
    output_path = os.path.join(output_dir, "temperature-plan.json")
    with open(output_path, "w") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate supervised temperature-characterization sweeps")
    parser.add_argument("--temperatures", required=True)
    parser.add_argument("--k-start", type=float, default=0.0)
    parser.add_argument("--k-stop", type=float, default=0.08)
    parser.add_argument("--k-step", type=float, default=0.01)
    parser.add_argument("--cycles", type=int, default=6)
    parser.add_argument("--restore-advance", type=float, required=True)
    parser.add_argument("--temperature-tolerance", type=float, default=2.0)
    parser.add_argument("--material-label")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    result = build_temperature_plan(
        args.output_dir, parse_temperatures(args.temperatures),
        decimal_range(args.k_start, args.k_stop, args.k_step),
        args.cycles, args.restore_advance,
        args.temperature_tolerance, args.material_label)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
