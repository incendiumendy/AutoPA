"""Generate a bounded Klipper Pressure Advance sweep and its analysis plan."""
import argparse
import json
import math
import os


def decimal_range(start, stop, step):
    if step <= 0:
        raise ValueError("K step must be greater than zero")
    count = int(math.floor((stop - start) / step + 1e-9)) + 1
    if count < 1:
        raise ValueError("K stop must be greater than or equal to K start")
    return [round(start + index * step, 10) for index in range(count)]


POSITION_BOUNDS = {
    "start_x": (0.0, 500.0),
    "start_y": (0.0, 500.0),
    "start_z": (10.0, 300.0),
    "prime_e": (0.0, 20.0),
}

# Slow settle extrusion appended after the main prime: 25 % of the prime,
# bounded so tiny primes still get a useful settle and large primes stay
# reasonable.
PRIME_SETTLE_FRACTION = 0.25
PRIME_SETTLE_MIN_MM = 1.0
PRIME_SETTLE_MAX_MM = 4.0


def prime_settle_e(prime_e):
    """Slow settle extrusion (mm E) that follows the main prime."""
    if not prime_e:
        return 0.0
    return min(
        PRIME_SETTLE_MAX_MM,
        max(PRIME_SETTLE_MIN_MM, prime_e * PRIME_SETTLE_FRACTION))


def validated_position(start_x=None, start_y=None, start_z=None,
                       prime_e=0.0):
    values = {
        "start_x": start_x,
        "start_y": start_y,
        "start_z": start_z,
        "prime_e": prime_e,
    }
    checked = {}
    for key, value in values.items():
        if value is None:
            checked[key] = None
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("%s must be a finite number" % key)
        low, high = POSITION_BOUNDS[key]
        if not low <= value <= high:
            raise ValueError(
                "%s must be between %s and %s" % (key, low, high))
        checked[key] = float(value)
    return checked


def build_position_preamble(start_x=None, start_y=None, start_z=None,
                            prime_e=0.0, current_z=None):
    """Optional bounded absolute positioning plus a short pressure prime.

    Works on printers without a purge container: the caller picks any safe
    spot (catch tray, free drop zone) and the sweep raises Z first so the
    extruded strand can never reach the nozzle again.

    The Z lift is emitted only when it increases the nozzle-to-bed gap:
    when ``current_z`` is known and already at or above ``start_z``, no Z
    move is emitted at all, so the bed or gantry never travels toward the
    nozzle. Returns ``(lines, z_lift)``.
    """
    if current_z is not None:
        if (not isinstance(current_z, (int, float))
                or isinstance(current_z, bool)
                or not math.isfinite(current_z)):
            raise ValueError("current_z must be a finite number")
        current_z = float(current_z)
    pos = validated_position(start_x, start_y, start_z, prime_e)
    lines = []
    z_lift = False
    if pos["start_z"] is not None:
        if current_z is None or current_z < pos["start_z"]:
            lines.append("G90")
            lines.append("G1 Z%.4f F600" % pos["start_z"])
            lines.append("G91")
            z_lift = True
    if pos["start_x"] is not None or pos["start_y"] is not None:
        x_part = " X%.4f" % pos["start_x"] if pos["start_x"] is not None else ""
        y_part = " Y%.4f" % pos["start_y"] if pos["start_y"] is not None else ""
        lines.append("G90")
        lines.append("G1%s%s F6000" % (x_part, y_part))
        lines.append("G91")
    if pos["prime_e"]:
        # Two-stage prime: the main extrusion refills the melt chamber, the
        # dwell lets ooze and pressure relax, then a slow settle extrusion
        # rebuilds stable nozzle pressure right before the first measured
        # cycle. This removes the first-cycle artefacts seen after the hot
        # end sat idle (empty chamber from oozing).
        lines.append("G1 E%.5f F300" % pos["prime_e"])
        lines.append("G4 P800")
        lines.append("G1 E%.5f F120" % prime_settle_e(pos["prime_e"]))
        lines.append("G4 P300")
    return lines, z_lift


def build_sweep(k_values, cycles, slow_e_speed=0.8, fast_e_speed=8.0,
                slow_duration=1.0, fast_duration=0.25, x_travel=8.0,
                restore_advance=None, min_z=10.0,
                target_temperature=None, temperature_tolerance=2.0,
                start_x=None, start_y=None, start_z=None, prime_e=0.0,
                current_z=None):
    if not k_values:
        raise ValueError("At least one pressure advance value is required")
    if any(value < 0.0 or value > 0.2 for value in k_values):
        raise ValueError("Pressure advance values must be between 0 and 0.2")
    if restore_advance is None or not 0.0 <= restore_advance <= 0.2:
        raise ValueError("A restore advance between 0 and 0.2 is required")
    if cycles < 3 or cycles > 30:
        raise ValueError("Cycles must be between 3 and 30")
    for name, value in (
            ("slow E speed", slow_e_speed),
            ("fast E speed", fast_e_speed),
            ("slow duration", slow_duration),
            ("fast duration", fast_duration),
            ("X travel", x_travel)):
        if value <= 0:
            raise ValueError("%s must be greater than zero" % name)
    if fast_e_speed <= slow_e_speed:
        raise ValueError("Fast E speed must exceed slow E speed")
    if x_travel > 30.0:
        raise ValueError("X travel is limited to 30mm")
    if (target_temperature is not None
            and not 0.0 < target_temperature <= 500.0):
        raise ValueError("Target temperature must be between 0 and 500C")
    if not 0.0 < temperature_tolerance <= 20.0:
        raise ValueError("Temperature tolerance must be between 0 and 20C")

    slow_e = slow_e_speed * slow_duration
    fast_e = fast_e_speed * fast_duration
    slow_xy_speed = x_travel / slow_duration
    fast_xy_speed = x_travel / fast_duration
    slow_feed = slow_xy_speed * 60.0
    fast_feed = fast_xy_speed * 60.0
    validation = "AUTOPA_VALIDATE X_TRAVEL=%.4f MIN_Z=%.4f" % (
        x_travel, min_z)
    if target_temperature is not None:
        validation += " TARGET_TEMP=%.2f TEMP_TOLERANCE=%.2f" % (
            target_temperature, temperature_tolerance)
    lines = [
        "; AutoPA Klipper sweep - generated file",
        "; Run only with the nozzle in free air and observe the printer.",
        "M400",
        validation,
        "SAVE_GCODE_STATE NAME=AUTOPA_SWEEP",
        "M83",
        "G91",
    ]
    preamble, z_lift = build_position_preamble(
        start_x, start_y, start_z, prime_e, current_z=current_z)
    lines.extend(preamble)
    lines.append("AUTOPA_MARK EVENT=sweep_start VALUE=%.6f" % k_values[0])
    segments = []
    offset = 0.0
    for k_index, k_value in enumerate(k_values):
        lines.extend([
            "SET_PRESSURE_ADVANCE ADVANCE=%.6f" % k_value,
            "AUTOPA_MARK EVENT=k_start VALUE=%.6f" % k_value,
        ])
        segment = {
            "k": k_value,
            "index": k_index,
            "start_offset_s": offset,
            "cycles": cycles,
            "cycle_period_s": slow_duration + fast_duration,
        }
        segments.append(segment)
        for cycle in range(cycles):
            lines.extend([
                "AUTOPA_MARK EVENT=slow_start VALUE=%.6f:%d"
                % (k_value, cycle),
                "G1 X%.4f E%.5f F%.3f"
                % (x_travel, slow_e, slow_feed),
                "AUTOPA_MARK EVENT=fast_start VALUE=%.6f:%d"
                % (k_value, cycle),
                "G1 X%.4f E%.5f F%.3f"
                % (-x_travel, fast_e, fast_feed),
            ])
            offset += slow_duration + fast_duration
        lines.append("AUTOPA_MARK EVENT=k_end VALUE=%.6f" % k_value)
    lines.extend([
        "M400",
        "AUTOPA_MARK EVENT=sweep_end VALUE=%.6f" % k_values[-1],
        "SET_PRESSURE_ADVANCE ADVANCE=%.6f" % restore_advance,
        "RESTORE_GCODE_STATE NAME=AUTOPA_SWEEP",
        "; End AutoPA sweep",
    ])
    plan = {
        "format_version": 1,
        "firmware": "klipper",
        "k_values": k_values,
        "cycles_per_k": cycles,
        "slow_e_speed_mm_s": slow_e_speed,
        "fast_e_speed_mm_s": fast_e_speed,
        "slow_duration_s": slow_duration,
        "fast_duration_s": fast_duration,
        "x_travel_mm": x_travel,
        "restore_advance": restore_advance,
        "minimum_z_mm": min_z,
        "target_temperature_c": target_temperature,
        "temperature_tolerance_c": temperature_tolerance,
        "start_x_mm": start_x,
        "start_y_mm": start_y,
        "start_z_mm": start_z,
        "prime_e_mm": prime_e,
        "prime_settle_e_mm": prime_settle_e(prime_e),
        "current_z_mm": current_z,
        "z_lift": z_lift,
        "estimated_sweep_duration_s": offset,
        "filament_length_mm": (
            len(k_values) * cycles * (slow_e + fast_e) + (prime_e or 0.0)
            + prime_settle_e(prime_e)),
        "segments": segments,
    }
    return "\n".join(lines) + "\n", plan


def main():
    parser = argparse.ArgumentParser(
        description="Generate a safe, marked Klipper AutoPA sweep")
    parser.add_argument("--k-start", type=float, default=0.0)
    parser.add_argument("--k-stop", type=float, default=0.08)
    parser.add_argument("--k-step", type=float, default=0.01)
    parser.add_argument("--cycles", type=int, default=6)
    parser.add_argument("--slow-e-speed", type=float, default=0.8)
    parser.add_argument("--fast-e-speed", type=float, default=8.0)
    parser.add_argument("--slow-duration", type=float, default=1.0)
    parser.add_argument("--fast-duration", type=float, default=0.25)
    parser.add_argument("--x-travel", type=float, default=8.0)
    parser.add_argument("--min-z", type=float, default=10.0)
    parser.add_argument("--restore-advance", type=float, required=True)
    parser.add_argument("--target-temperature", type=float)
    parser.add_argument("--temperature-tolerance", type=float, default=2.0)
    parser.add_argument("--start-x", type=float)
    parser.add_argument("--start-y", type=float)
    parser.add_argument("--start-z", type=float)
    parser.add_argument("--prime-e", type=float, default=0.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    gcode, plan = build_sweep(
        decimal_range(args.k_start, args.k_stop, args.k_step),
        args.cycles, args.slow_e_speed, args.fast_e_speed,
        args.slow_duration, args.fast_duration, args.x_travel,
        args.restore_advance, args.min_z,
        args.target_temperature, args.temperature_tolerance,
        args.start_x, args.start_y, args.start_z, args.prime_e)
    output = os.path.abspath(args.output)
    with open(output, "w") as handle:
        handle.write(gcode)
    plan_path = os.path.splitext(output)[0] + ".json"
    with open(plan_path, "w") as handle:
        json.dump(plan, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({
        "gcode": output,
        "plan": plan_path,
        "estimated_sweep_duration_s": plan["estimated_sweep_duration_s"],
        "filament_length_mm": plan["filament_length_mm"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
