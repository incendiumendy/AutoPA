# Optional accelerometers

AutoPA can record force alone or add a Klipper accelerometer as a diagnostic
motion channel. The accelerometer does not control the printer and is not
required for the Pressure Advance step-response metric.

## Supported Klipper drivers

| `--accelerometer-type` | Klipper configuration section | API endpoint |
| --- | --- | --- |
| `lis2dw` | `[lis2dw]` or `[lis2dw name]` | `lis2dw/dump_lis2dw` |
| `lis3dh` | `[lis3dh]` or `[lis3dh name]` | `lis2dw/dump_lis2dw` |
| `adxl345` | `[adxl345]` or `[adxl345 name]` | `adxl345/dump_adxl345` |
| `mpu9250` | `[mpu9250]` or a compatible MPU/ICM driver | `mpu9250/dump_mpu9250` |
| `none` | no accelerometer required | no subscription |

`--accelerometer` is the configured Klipper sensor name, not the MCU name.
For example, `[lis2dw toolboard_t0]` uses `toolboard_t0`, while an unqualified
`[adxl345]` normally uses `adxl345`.

## Examples

EBB42 Gen2 LIS2DW:

```sh
PYTHONPATH=src python3 -m autopa.sync_recorder \
  --alps-device /dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_YOUR_ID-if00 \
  --accelerometer-type lis2dw \
  --accelerometer toolboard_t0 \
  --duration 10 \
  --name lis2dw_test
```

ADXL345:

```sh
PYTHONPATH=src python3 -m autopa.sync_recorder \
  --alps-device /dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_YOUR_ID-if00 \
  --accelerometer-type adxl345 \
  --accelerometer adxl345 \
  --duration 10 \
  --name adxl345_test
```

Force-only:

```sh
PYTHONPATH=src python3 -m autopa.sync_recorder \
  --alps-device /dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_YOUR_ID-if00 \
  --accelerometer-type none \
  --duration 10 \
  --name force_only
```

In force-only mode AutoPA still records Klipper clock pairs, temperature,
Pressure Advance, print state, markers and commanded extruder motion.
`acceleration.csv` contains only its header, `combined.csv` uses the
regularized ALPS sample timebase, and acceleration quality gates are skipped.
The dashboard labels the optional channel as disabled instead of reporting a
fault.

An invalid driver/name pair fails only the capture. AutoPA does not pause or
cancel an ordinary print and never substitutes a different sensor
automatically.
