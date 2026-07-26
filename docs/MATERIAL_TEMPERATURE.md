# Filament consistency and temperature characterization

## What AutoPA can determine

At a fixed nozzle, flow pattern and cooling setup, AutoPA can compare:

- optimal PA estimate at each tested temperature;
- pressure step-response cost;
- cycle-to-cycle pressure variation;
- signal-to-noise ratio;
- extrusion-pressure loss events;
- measured versus requested nozzle temperature.

This produces a **sensor-derived process window**, not a universally perfect
temperature.

The ALPS does not directly measure stringing, polymer degradation, surface
quality, inter-layer adhesion, dimensional accuracy, moisture content or
material identity. Those properties still require printed visual and
mechanical tests.

## Filament consistency check

After a synchronized, aligned and analysed extrusion sweep:

```sh
PYTHONPATH=src python3 -m autopa.material check \
  ~/printer_data/autopa/<dataset>
```

`material_check.json` reports:

- `consistent`, `warning` or `unavailable`;
- temperature stability and target error;
- selected PA and estimator cost;
- valid cycle count;
- pressure-amplitude MAD as a fraction of median amplitude;
- pressure signal-to-noise ratio;
- pressure-loss events.

Current conservative gates include:

- at least three valid cycles;
- nozzle temperature span no greater than 3 °C;
- median temperature within 2 °C of the requested target;
- pressure-cycle MAD no greater than 25% before a warning;
- signal-to-noise ratio of at least 6 before a warning;
- no lost-extrusion-pressure event.

A warning may indicate inconsistent feed, a contaminated nozzle, unstable
temperature, changing material, bubbles or mechanical disturbance. It does
not diagnose moisture or a specific fault by itself.

## Generate temperature-bound test files

Choose a safe range from the filament manufacturer's specification. The
generator creates one independent file per temperature:

```sh
PYTHONPATH=src python3 -m autopa.temperature_plan \
  --temperatures 200,210,220 \
  --k-start 0.01 \
  --k-stop 0.05 \
  --k-step 0.02 \
  --cycles 3 \
  --restore-advance 0.03 \
  --material-label my_filament \
  --output-dir temperature-test
```

Important safety properties:

- at least three distinct temperatures are required;
- the files do not issue `M104` or `M109`;
- the operator heats and stabilizes the hotend manually;
- `AUTOPA_VALIDATE` checks actual and requested temperature within ±2 °C;
- a mismatch rejects that calibration file before motion;
- each file restores the supplied PA value;
- no result is applied automatically.

For a serious characterization use more cycles and a PA range appropriate for
the extruder after the three-cycle smoke run succeeds.

## Compare temperatures

Process every dataset in this order:

```sh
python3 -m autopa.align <dataset>
python3 -m autopa.quality <dataset>
python3 -m autopa.analyze <dataset>
python3 -m autopa.filament <dataset>
python3 -m autopa.material check <dataset>
```

Then compare at least three temperature datasets:

```sh
PYTHONPATH=src python3 -m autopa.material compare-temperatures \
  <dataset-200C> <dataset-210C> <dataset-220C> \
  --output temperature-comparison.json
```

The experimental sensor score weights:

- 50% PA step-response cost;
- 35% cycle-to-cycle pressure variation;
- 15% inverse signal-to-noise ratio.

The output contains a PA-versus-temperature table. A temperature and matching
PA are recommended only when the best tested result lies inside the tested
range. If the best result is the coldest or hottest point, AutoPA reports the
best tested value but requests a carefully chosen wider or shifted range.

## Reproducibility requirements

Keep the filament spool, nozzle, hotend, extrusion speeds, X movement,
acceleration, fan state, PA grid, Smooth Time, ALPS mounting and purge handling
constant across the comparison.

Repeat an apparent optimum on another day and validate it with a conventional
printed temperature/PA test before saving it to a slicer filament profile.

All results remain advisory and `printer_action` remains `none`.

## Included SUNLU ABS profile

The dashboard's ABS profile is currently seeded for SUNLU ABS Green,
1.75 mm:

- nozzle: 250–280 °C;
- bed: 80–100 °C;
- print speed: 50–200 mm/s;
- filament diameter: 1.75 mm.

These ranges are based on the linked SUNLU ABS product information from
[3DJake](https://www.3djake.at/sunlu/abs-black-9) and SUNLU's own
[ABS printing guide](https://store.sunlu.com/hu-es/blogs/3d-printing-guide/abs-filament-guide-beginner-to-advanced-3d-printing).
They define the permitted characterization envelope, not a single optimum.
Start the supervised test at the slower/lower-temperature end and keep the
printer enclosed and ventilated.
