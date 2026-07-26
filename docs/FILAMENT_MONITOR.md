# Advisory filament pressure-loss detection

## What can be detected

The ALPS cannot identify a broken filament directly. It can detect the more
general physical symptom:

> Klipper continues commanding positive extrusion, but nozzle back-pressure
> collapses and remains near the no-flow baseline.

Possible causes include:

- filament broken after a conventional runout switch;
- empty feed path;
- filament stripped by the drive gear;
- disconnected Bowden path;
- severe loss of material transport.

A load cell alone cannot reliably distinguish those causes. A filament switch
or motion encoder remains the best complementary signal.

## Additional Klipper signal

The recorder subscribes read-only to:

```text
motion_report/dump_trapq name=extruder
```

`extruder_motion.csv` stores exact Klipper `print_time`, segment duration,
commanded velocity, acceleration, position, direction and whether Pressure
Advance is active. Alignment reconstructs:

- `commanded_e_velocity_mm_s`;
- `pressure_advance_active`.

This prevents travel moves, retractions and intentionally idle periods from
being interpreted as filament loss.

## Conservative detector

`autopa.filament`:

1. learns a no-flow force baseline from periods with nearly zero commanded E;
2. learns a robust pressure-per-extrusion-velocity reference from valid
   positive extrusion;
3. ignores the first 0.5 seconds after extrusion starts or changes speed
   substantially;
4. requires at least 0.5 mm/s commanded E;
5. marks pressure as lost only below 15% of the learned reference;
6. requires the condition to persist for at least 1.5 seconds;
7. resets suspicion across sensor gaps above 100 ms.

Run it after alignment and quality analysis:

```sh
PYTHONPATH=src python3 -m autopa.filament \
  ~/printer_data/autopa/<dataset>
```

The result is written to `filament_diagnostics.json`.

## Fail-open behavior

- Every event is `advisory`.
- `printer_action` is always `none`.
- No `PAUSE`, `CANCEL_PRINT` or `M112` is sent.
- Missing extrusion telemetry or an invalid dataset disables detection.
- A short pressure dip is ignored.
- A sensor gap resets the confirmation timer instead of confirming a fault.

Future Moonraker integration may send an informational notification. Automatic
pause remains out of scope unless it becomes a separate, explicit opt-in with
independent sensor confirmation.

## Validation status

Synthetic tests cover:

- sustained pressure loss while extrusion continues: detected;
- short pressure loss below the confirmation time: ignored;
- no positive extrusion reference: detector unavailable;
- every detected event retains `printer_action: none`.

The RatOS printer accepted the read-only extruder trapq subscription during an
idle three-second capture with zero errors. Detection on real extrusion remains
to be validated during the supervised smoke sweep.
