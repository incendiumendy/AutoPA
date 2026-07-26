# Adaptive PA and Auto-Retract validation

AutoPA includes an experimental live estimator for Pressure Advance and
firmware retraction. Its first purpose is measurement and dry-run validation,
not unattended closed-loop control.

## What the pressure display means

The FLY-ALPS card shows:

- the current filtered ADC value;
- a learned no-flow baseline;
- the signed difference from that baseline in `counts`;
- a locally normalized percentage used by the estimator.

The large value is therefore **relative nozzle load**, not Newtons or a
calibrated pressure unit. Mechanical preload, mounting and hotend temperature
change the absolute ALPS value. Use the project calibration workflow before
interpreting it as physical force. For adaptive timing and residual-pressure
comparison, the local baseline and normalized signal are sufficient.

## Three modes

1. `off` keeps both adaptive options disabled and sends no G-code.
2. `dry_run` observes force, Klipper extrusion motion, temperature and the
   optional accelerometer. It displays suggestions but sends no G-code.
3. `apply` can send bounded runtime changes during an active print.

`apply` is deliberately transient. It is never restored from the saved control
file after a service restart.

## Independent locks

Applying a value requires all of the following:

- at least Adaptive PA or Auto-Retract is enabled;
- the service operator has explicitly set
  `AUTOPA_ALLOW_PRINTER_COMMANDS=1`;
- the dashboard operator enters the exact phrase `AUTOPA VALIDIEREN`;
- Klipper reports `printing`;
- fresh, plausible measurement evidence is available.

Arming expires after 30 minutes. The shipped systemd service keeps the
server-side flag at `0`, which makes the initial installation dry-run only.

## Hard bounds

The backend, not the browser, validates every setting:

| Setting | Default | Hard accepted range |
| --- | ---: | ---: |
| PA | 0.000 to 0.120 | 0.000 to 0.200 |
| PA step | 0.002 | 0.0001 to 0.020 |
| PA total deviation from start | 0.010 | 0.0001 to 0.050 |
| Retract length | 0.20 to 1.50 mm | 0.00 to 10.00 mm |
| Retract step | 0.05 mm | 0.01 to 0.50 mm |
| Retract total deviation from start | 0.30 mm | 0.01 to 1.00 mm |
| Minimum time between commands | 30 s | 10 to 600 s |
| Required PA windows | 5 | 3 to 100 |
| Required retract events | 5 | 3 to 100 |

The control loop accepts only finite numbers and rejects unknown settings.

## Data gates

No suggestion is applied when any of these is true:

- force data is missing or older than 0.5 seconds;
- force sampling is below 1,000 Hz;
- Klipper extrusion motion or its synchronized clock is missing;
- the hotend differs from its target by more than 2 °C;
- an accelerometer reports errors or overflows;
- measured acceleration exceeds the configured disturbance limit;
- not enough repeated PA windows or retract events exist.

An accelerometer is helpful for rejecting mechanical disturbances but remains
optional. Supported recorder endpoints include LIS2DW, LIS3DH, ADXL345 and
MPU9250.

## Auto-Retract limitation

Auto-Retract requires Klipper's `[firmware_retraction]` object and uses only:

```text
SET_RETRACTION RETRACT_LENGTH=<bounded value>
```

It affects future `G10`/`G11` commands. If the slicer writes retractions as raw
extruder moves such as `G1 E-0.8`, Klipper firmware retraction is bypassed and
AutoPA cannot alter those moves. Enable “firmware retraction” in the slicer for
an Auto-Retract validation print.

## First validation print

1. Keep `AUTOPA_ALLOW_PRINTER_COMMANDS=0`.
2. Start a synchronized AutoPA recording that covers the whole test.
3. Open `/autopa/`, enable Adaptive PA and Auto-Retract, and select
   `Dry-Run starten`.
4. Confirm the pressure card has a stable zero point while no filament flows
   and reacts visibly during extrusion.
5. Print a small, non-critical model with repeated acceleration and `G10/G11`
   retractions.
6. Review data freshness, PA windows, retract events, normalized pressure and
   the proposed values. `Änderungen` must stay `0`.
7. Repeat the dry-run if signals are stale, temperature is unstable or
   proposals do not converge.

Only after this evidence is reviewed should a supervised bounded-apply test be
considered. Keep emergency stop available, use a disposable test model and
remain at the printer.

## Runtime behavior

The controller may send only:

```text
SET_PRESSURE_ADVANCE ADVANCE=<bounded value>
SET_RETRACTION RETRACT_LENGTH=<bounded value>
```

It never sends pause, cancel, emergency stop, heater, motion or
`SAVE_CONFIG`. Sensor/controller faults stop further updates and allow the
print to continue. On manual disarm, arming expiry or normal print completion,
values actually changed by AutoPA are restored to their captured starting
runtime values.
