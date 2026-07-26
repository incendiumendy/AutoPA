# Per-machine ALPS force calibration

## Why calibration is per machine

Absolute ALPS counts depend on the individual strain gauges, amplifier,
hotend mechanics, mounting torque, cable forces, temperature and load
direction. Two otherwise identical printers may therefore report different
offsets, polarity and counts per unit force.

AutoPA handles this in two layers:

1. Every PA cycle calculates a local slow-flow baseline and normalizes its step
   response. PA analysis therefore does not assume a universal raw count.
2. An optional persistent multi-point calibration converts counts to grams and
   Newtons and provides machine-specific noise and linearity diagnostics.

Raw `force.csv` data is never rewritten. Calibration only adds derived columns
to `combined.csv`.

## Safe reference-load acquisition

Use a suitable force gauge or a mechanically constrained calibration fixture.
Do not place loose weights on a nozzle, do not hold a weight above the bed and
do not automate Z motion against a scale as part of this project.

For every capture:

- keep the same hotend, mounting, cable routing and load direction;
- keep the toolhead stationary;
- apply the force axially and avoid side loading;
- use the same temperature state and record it;
- wait until the applied load is stable;
- record at least five seconds;
- remove the reference fixture before homing or printing.

The software never moves the printer during calibration acquisition.

Capture one unloaded state and at least one known load. Two or more non-zero
loads are strongly recommended because they expose non-linearity:

```sh
PYTHONPATH=src python3 -m autopa.sync_recorder \
  --alps-device /dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_YOUR_ID-if00 \
  --duration 5 --name calibration_zero

# Repeat with stable, known axial reference loads:
# --name calibration_100g
# --name calibration_200g
```

## Build a calibration

```sh
PYTHONPATH=src python3 -m autopa.calibration \
  --zero ~/printer_data/autopa/<zero-dataset> \
  --point 100=~/printer_data/autopa/<100g-dataset> \
  --point 200=~/printer_data/autopa/<200g-dataset> \
  --temperature-c 25 \
  --label my_alps_cold \
  --output ~/printer_data/config/autopa-calibration.json
```

The fitter accepts either polarity. A force that reduces the counts is stored
as `polarity: decreasing` but still converts the applied reference direction
to positive grams.

The file contains:

- zero-force offset;
- signed counts per gram;
- grams and Newtons per count;
- maximum observed noise;
- a six-MAD detection limit in grams;
- fit RMS, maximum residual and R²;
- every reference point and its sample count;
- a content-derived calibration ID.

The calibration is invalid when the reference span is less than ten times the
measured noise. With three or more reference levels it is also invalid when
the maximum fit residual exceeds 2% of the count span or R² is below 0.995.

## Use the calibration

```sh
PYTHONPATH=src python3 -m autopa.align \
  ~/printer_data/autopa/<dataset> \
  --calibration ~/printer_data/config/autopa-calibration.json

PYTHONPATH=src python3 -m autopa.quality \
  ~/printer_data/autopa/<dataset> \
  --calibration ~/printer_data/config/autopa-calibration.json
```

`combined.csv` then contains `force_raw_grams` and
`force_filtered_grams`. `alignment.json` records the calibration ID and force
unit. The analyser prefers calibrated filtered force when present, while its
dimensionless overshoot and area ratios remain comparable across machines.

## When to recalibrate

Create a new calibration after:

- replacing or remounting the hotend or strain-gauge assembly;
- changing mounting torque or cable routing;
- changing ALPS firmware or measurement filtering;
- a large persistent zero/noise change;
- mechanical damage or overload;
- using a temperature state whose response differs materially.

Never overwrite an old calibration without retaining its ID with the related
datasets. Calibration files are printer-specific and should normally remain
outside the Git repository.
