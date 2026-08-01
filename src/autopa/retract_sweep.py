"""Generate a bounded Klipper firmware-retraction sweep and its analysis plan.

The sweep varies RETRACT_LENGTH through Klipper's [firmware_retraction]
object and uses G10/G11 so the recorded ALPS force shows how much nozzle
pressure remains after each retraction and how cleanly extrusion restarts.
It never changes PA and always restores the starting retraction length.
"""
import argparse
import json
import os

from .sweep import build_position_preamble, decimal_range, prime_settle_e


MAX_RETRACT_MM = 10.0

# Firmware-retraction speeds outside this band are rejected. The lower bound
# keeps a cycle from dwelling so long that the melt relaxes on its own and the
# measurement stops being about the retraction; the upper bound is where
# extruders start skipping on stiff filament. The ALPS cannot see skipping -
# there is no encoder - so the range must stay conservative rather than rely
# on the analysis to notice damage.
MIN_RETRACT_SPEED_MM_S = 5.0
MAX_RETRACT_SPEED_MM_S = 120.0


def build_retract_sweep(retract_values, cycles, e_speed=1.5,
                        extrude_duration=1.2, settle_s=1.0, x_travel=8.0,
                        retract_speed=35.0, restore_retract=None, min_z=10.0,
                        target_temperature=None, temperature_tolerance=2.0,
                        start_x=None, start_y=None, start_z=None,
                        prime_e=0.0, current_z=None, speed_values=None,
                        restore_retract_speed=None):
    # speed_values turns this into a retraction-speed sweep: the length is
    # held at retract_values[0] and every candidate speed is measured with the
    # same three metrics. Material viscosity changes how fast the melt can
    # follow the filament, so the best length at one speed is not the best
    # length at another - but sweeping both as a grid costs 2.5x the time and
    # filament, so the two run as separate stages.
    sweep_speed = bool(speed_values)
    if sweep_speed and len(retract_values) != 1:
        raise ValueError(
            "A speed sweep needs exactly one retract length to hold")
    if not retract_values:
        raise ValueError("At least one retract length is required")
    if any(value < 0.0 or value > MAX_RETRACT_MM for value in retract_values):
        raise ValueError(
            "Retract lengths must be between 0 and %.1f mm" % MAX_RETRACT_MM)
    if sweep_speed:
        if any(not MIN_RETRACT_SPEED_MM_S <= value <= MAX_RETRACT_SPEED_MM_S
               for value in speed_values):
            raise ValueError(
                "Retract speeds must be between %.0f and %.0f mm/s"
                % (MIN_RETRACT_SPEED_MM_S, MAX_RETRACT_SPEED_MM_S))
        if (restore_retract_speed is None
                or not MIN_RETRACT_SPEED_MM_S <= restore_retract_speed
                <= MAX_RETRACT_SPEED_MM_S):
            raise ValueError(
                "A restore retract speed between %.0f and %.0f mm/s is "
                "required" % (MIN_RETRACT_SPEED_MM_S, MAX_RETRACT_SPEED_MM_S))
    if (restore_retract is None
            or not 0.0 <= restore_retract <= MAX_RETRACT_MM):
        raise ValueError(
            "A restore retract length between 0 and %.1f mm is required"
            % MAX_RETRACT_MM)
    if cycles < 3 or cycles > 30:
        raise ValueError("Cycles must be between 3 and 30")
    for name, value in (
            ("E speed", e_speed),
            ("extrude duration", extrude_duration),
            ("settle time", settle_s),
            ("retract speed", retract_speed),
            ("X travel", x_travel)):
        if value <= 0:
            raise ValueError("%s must be greater than zero" % name)
    if extrude_duration < 0.6:
        raise ValueError(
            "Extrude duration must be at least 0.6s for stable pressure")
    if settle_s < 0.6:
        raise ValueError(
            "Settle time must be at least 0.6s for a residual measurement")
    if x_travel > 30.0:
        raise ValueError("X travel is limited to 30mm")
    if (target_temperature is not None
            and not 0.0 < target_temperature <= 500.0):
        raise ValueError("Target temperature must be between 0 and 500C")
    if not 0.0 < temperature_tolerance <= 20.0:
        raise ValueError("Temperature tolerance must be between 0 and 20C")

    extrude_e = e_speed * extrude_duration
    feed = x_travel / extrude_duration * 60.0
    settle_ms = int(round(settle_s * 1000.0))
    validation = "AUTOPA_VALIDATE X_TRAVEL=%.4f MIN_Z=%.4f" % (
        x_travel, min_z)
    if target_temperature is not None:
        validation += " TARGET_TEMP=%.2f TEMP_TOLERANCE=%.2f" % (
            target_temperature, temperature_tolerance)
    lines = [
        "; AutoPA firmware-retraction sweep - generated file",
        "; Requires Klipper [firmware_retraction] and the AutoPA recorder.",
        "; Run only with the nozzle in free air and observe the printer.",
        "M400",
        validation,
        "SAVE_GCODE_STATE NAME=AUTOPA_RETRACT",
        "M83",
        "G91",
    ]
    preamble, z_lift = build_position_preamble(
        start_x, start_y, start_z, prime_e, current_z=current_z)
    lines.extend(preamble)
    candidates = speed_values if sweep_speed else retract_values
    held_length = retract_values[0]
    # The analysis reads this marker to learn which variable the cycle values
    # belong to. Without it a speed sweep would be ranked and reported as a
    # length, and the auto-apply path would push a speed number into
    # SET_RETRACTION RETRACT_LENGTH.
    lines.append(
        "AUTOPA_MARK EVENT=retract_sweep_mode VALUE=%s"
        % ("speed" if sweep_speed else "length"))
    lines.append(
        "AUTOPA_MARK EVENT=retract_sweep_start VALUE=%.4f" % candidates[0])
    segments = []
    offset = 0.0
    for r_index, r_value in enumerate(candidates):
        # UNRETRACT_EXTRA_LENGTH is pinned to zero so every candidate is
        # evaluated symmetrically. In a speed sweep the retract and unretract
        # speeds move together: splitting them would need a second dimension,
        # and the restart metrics cannot attribute a difference to one of
        # them on their own.
        if sweep_speed:
            lines.append(
                "SET_RETRACTION RETRACT_LENGTH=%.4f RETRACT_SPEED=%.4f "
                "UNRETRACT_SPEED=%.4f UNRETRACT_EXTRA_LENGTH=0"
                % (held_length, r_value, r_value))
            cycle_speed = r_value
        else:
            lines.append(
                "SET_RETRACTION RETRACT_LENGTH=%.4f UNRETRACT_EXTRA_LENGTH=0"
                % r_value)
            cycle_speed = retract_speed
        lines.append("AUTOPA_MARK EVENT=r_start VALUE=%.4f" % r_value)
        moved_mm = held_length if sweep_speed else r_value
        retract_time = moved_mm / cycle_speed
        cycle_period = 2.0 * extrude_duration + settle_s + 2.0 * retract_time
        segments.append({
            "retract_length_mm": held_length if sweep_speed else r_value,
            "retract_speed_mm_s": cycle_speed,
            "swept_value": r_value,
            "index": r_index,
            "start_offset_s": offset,
            "cycles": cycles,
            "cycle_period_s": cycle_period,
        })
        for cycle in range(cycles):
            marker = "%.4f:%d" % (r_value, cycle)
            lines.extend([
                "G1 X%.4f E%.5f F%.3f" % (x_travel, extrude_e, feed),
                "AUTOPA_MARK EVENT=retract_start VALUE=" + marker,
                "G10",
                "G4 P%d" % settle_ms,
                "AUTOPA_MARK EVENT=unretract_start VALUE=" + marker,
                "G11",
                "G1 X%.4f E%.5f F%.3f" % (-x_travel, extrude_e, feed),
                "AUTOPA_MARK EVENT=cycle_end VALUE=" + marker,
            ])
            offset += cycle_period
        lines.append("AUTOPA_MARK EVENT=r_end VALUE=%.4f" % r_value)
    restore = "SET_RETRACTION RETRACT_LENGTH=%.4f" % restore_retract
    if sweep_speed:
        # A speed sweep changed both speeds, so both must be put back or the
        # printer keeps the last candidate after the run.
        restore += " RETRACT_SPEED=%.4f UNRETRACT_SPEED=%.4f" % (
            restore_retract_speed, restore_retract_speed)
    lines.extend([
        "M400",
        "AUTOPA_MARK EVENT=retract_sweep_end VALUE=%.4f" % candidates[-1],
        restore,
        "RESTORE_GCODE_STATE NAME=AUTOPA_RETRACT",
        "; End AutoPA retraction sweep",
    ])
    plan = {
        "format_version": 1,
        "firmware": "klipper",
        "firmware_retraction_required": True,
        "swept_variable": "retract_speed" if sweep_speed else "retract_length",
        "speed_values_mm_s": list(speed_values) if sweep_speed else None,
        "held_retract_length_mm": held_length if sweep_speed else None,
        "restore_retract_speed_mm_s": (
            restore_retract_speed if sweep_speed else None),
        "retract_values_mm": retract_values,
        "cycles_per_value": cycles,
        "e_speed_mm_s": e_speed,
        "extrude_duration_s": extrude_duration,
        "settle_s": settle_s,
        "x_travel_mm": x_travel,
        "retract_speed_mm_s": retract_speed,
        "restore_retract_mm": restore_retract,
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
            len(candidates) * cycles * 2.0 * extrude_e
            + (prime_e or 0.0) + prime_settle_e(prime_e)),
        "segments": segments,
        "notes": ([
            "The sweep sets RETRACT_SPEED and UNRETRACT_SPEED together and "
            "restores both at the end.",
            "Speed is ranked mainly by restart deficit and overshoot after "
            "G11. Residual pressure barely separates speeds because the "
            "settle window is long enough for any of them to relax.",
            "The ALPS cannot detect a skipping or ground extruder - there "
            "is no encoder - so a fast candidate that damages filament can "
            "still score well. Treat the result as a starting point and "
            "watch the extruder during the run.",
        ] if sweep_speed else [
            "Retract and unretract move durations assume the configured "
            "[firmware_retraction] speeds; retract_speed is only used for "
            "the time estimate.",
            "The analysis ranks values by residual nozzle pressure during "
            "the settle window and by restart deficit after G11.",
            "The result is a measurement suggestion. Confirm the chosen "
            "length with a stringing test print before adopting it.",
        ]),
    }
    return "\n".join(lines) + "\n", plan


def main():
    parser = argparse.ArgumentParser(
        description="Generate a safe, marked Klipper AutoPA retraction sweep")
    parser.add_argument("--r-start", type=float, default=0.2)
    parser.add_argument("--r-stop", type=float, default=1.5)
    parser.add_argument("--r-step", type=float, default=0.1)
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--e-speed", type=float, default=1.5)
    parser.add_argument("--extrude-duration", type=float, default=1.2)
    parser.add_argument("--settle-s", type=float, default=1.0)
    parser.add_argument("--x-travel", type=float, default=8.0)
    parser.add_argument("--retract-speed", type=float, default=35.0)
    parser.add_argument("--min-z", type=float, default=10.0)
    parser.add_argument("--restore-retract", type=float, required=True)
    parser.add_argument("--target-temperature", type=float)
    parser.add_argument("--temperature-tolerance", type=float, default=2.0)
    parser.add_argument("--start-x", type=float)
    parser.add_argument("--start-y", type=float)
    parser.add_argument("--start-z", type=float)
    parser.add_argument("--prime-e", type=float, default=0.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    gcode, plan = build_retract_sweep(
        decimal_range(args.r_start, args.r_stop, args.r_step),
        args.cycles, args.e_speed, args.extrude_duration, args.settle_s,
        args.x_travel, args.retract_speed, args.restore_retract, args.min_z,
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
