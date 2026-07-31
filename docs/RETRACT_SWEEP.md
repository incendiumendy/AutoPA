# Supervised firmware-retraction sweep

`retract_sweep` generates a bounded, marked Klipper G-code file that varies
`RETRACT_LENGTH` through Klipper's `[firmware_retraction]` object. The ALPS
force recording shows how much nozzle pressure remains after each `G10` and
how cleanly extrusion restarts after each `G11`. `retract_analyze` ranks the
tested lengths from that recording.

The result is a measurement suggestion, not an automatic change. Nothing in
this workflow pauses, cancels or modifies a print, and the recommendation is
never applied automatically.

## Requirements

- Klipper `[firmware_retraction]` configured and working (`G10`/`G11`);
- the AutoPA Klipper extension (`AUTOPA_VALIDATE`, `AUTOPA_MARK`);
- a running synchronized AutoPA recording that covers the whole sweep;
- the nozzle in free air above a catch tray or a safe free-drop zone — a
  purge container is convenient but not required; any spot where the
  extruded strand can fall away without ever reaching the nozzle works.

## Test position and prime

Both sweeps accept an optional bounded start position and a pressure prime,
in the generator (`--start-x/--start-y/--start-z/--prime-e`) and in the
dashboard/tile payloads (`start_x`, `start_y`, `start_z`, `prime_e`):

- `start_z` (10–300 mm) raises the nozzle before anything is extruded; 50 mm
  keeps the filament pile far from the tip even without a container.
- `start_x`/`start_y` (0–500 mm) move to a chosen spot, for example above a
  catch tray clipped to the frame or over the bed edge.
- `prime_e` (0–20 mm) extrudes a few millimetres at print temperature so the
  first cycle measures stable pressure instead of refill.

Bounds are enforced again server-side; Klipper additionally rejects any move
outside the axis limits.

## Generate the sweep

First obtain the current retraction length from Klipper. It is mandatory as
`--restore-retract`, so the generated file restores that value at the end.

```sh
PYTHONPATH=src python3 -m autopa.retract_sweep \
  --r-start 0.2 \
  --r-stop 1.4 \
  --r-step 0.2 \
  --cycles 5 \
  --restore-retract 0.8 \
  --output autopa-retract-smoke.gcode
```

Every cycle:

1. moves X by +8 mm while extruding slowly to build steady nozzle pressure;
2. runs `G10` with the candidate length and dwells for one second while the
   residual pressure decays;
3. runs `G11` and moves X back while extrusion restarts.

`UNRETRACT_EXTRA_LENGTH` is pinned to zero for all candidates so the
comparison stays symmetric. Retract/unretract speeds come from the printer's
`[firmware_retraction]` configuration; `--retract-speed` is only used for the
duration estimate.

Before any sweep, follow the same checklist as the PA smoke sweep: home all
axes, nozzle at least 10 mm above the bed, filament at a safe extrusion
temperature, purge container in place, free +X travel verified, recorder
running, and remain at the printer with emergency stop available.
`AUTOPA_VALIDATE` rejects the file if axes are not homed, Z is too low, the
+X move would exceed the axis limit, or the hotend is too cold.

## Running the sweep from the dashboard

Instead of uploading a G-code file, the dashboard card "Rückzugs-Sweep" sends
the same bounded sweep directly to Moonraker (`/printer/gcode/script`). No
file is created on the printer.

- `GET /api/sweep` reports the lock state, the enforced bounds
  (r_start 0–5 mm, r_stop 0.05–10 mm, r_step 0.01–2 mm, 3–30 cycles, at most
  25 values and 4000 lines) and the last run or error.
- `POST /api/sweep/run` starts a sweep. It requires the literal phrase
  `AUTOPA VALIDIEREN`, the printer in `standby`, and the service started with
  `AUTOPA_ALLOW_PRINTER_COMMANDS=1`. Without that flag the button stays
  locked ("Server-seitig gesperrt").

The restore value is read automatically from Klipper's
`firmware_retraction.retract_length`, so the sweep always ends with the
printer's configured retraction length. The same safety rules as for the
generated file apply: homed axes, nozzle in free air over a purge container,
recorder running, operator present. The recommendation is still never
applied automatically.

## Analyze the recording

```sh
PYTHONPATH=src python3 -m autopa.align ~/printer_data/autopa/<dataset>
PYTHONPATH=src python3 -m autopa.quality ~/printer_data/autopa/<dataset>
PYTHONPATH=src python3 -m autopa.retract_analyze ~/printer_data/autopa/<dataset>
```

Each cycle is direction-normalized and contributes three measurements:

| Metric | Meaning | Better |
| --- | --- | --- |
| `residual_counts` | nozzle pressure remaining during the dwell after `G10` | lower |
| `restart_deficit_ratio` | pressure dip after `G11` before extrusion recovers | lower |
| `restart_overshoot_ratio` | pressure peak above the extrusion level right after `G11` | lower |

A cycle is excluded when its dwell is shorter than 0.5 s, its windows contain
too few samples, or its pressure amplitude is below three times the per-window
noise. A retract length needs at least three included cycles, and at least
three eligible lengths are compared. Metrics are normalized across the
eligible lengths and averaged into one cost; the lowest cost wins.

The recommendation is suppressed (fail-closed) when the quality gate of the
dataset did not pass, markers are missing or implausible, or too few cycles
are usable. The analysis artifact itself always sets `apply_automatically`
to `false` and `printer_action` to `none` — it never touches the printer.

## Bounded auto-apply

When a sweep is started from the dashboard or the Mainsail tile with
auto-apply enabled (the default), the service automatically captures the
sweep, runs the quality gate and the analysis, and applies the
recommendation **at runtime only** when it stays within the deviation limit:

| Sweep | Runtime command | Default limit | Hard cap |
| --- | --- | --- | --- |
| Retraction | `SET_RETRACTION RETRACT_LENGTH=<value>` | ±1.5 mm | ±3.0 mm |
| Pressure advance | `SET_PRESSURE_ADVANCE ADVANCE=<value>` | ±0.09 | ±0.2 |

The limit is configurable per run (`apply_bound`, tile field „Grenze" /
"Limit"). An apply happens only when the analysis produced a conclusive
recommendation; otherwise the runner records the skip reason
(`no_capture_dataset`, `no_recommendation`, `outside_bounds`,
`values_unavailable`, `analysis_failed`) in `lastApply` of the sweep status.
The applied value is **never persisted** — no `SAVE_CONFIG`, no Klipper
restart. Save it manually in Mainsail when you are happy with it.

## Adopting a value manually

Apply the suggested length manually, for example:

```text
SET_RETRACTION RETRACT_LENGTH=<value>
```

or by updating the slicer/profile. Confirm the choice with a stringing test
print before using it on real parts. Residual pressure is a proxy: it cannot
see surface stringing, seam appearance or layer adhesion.