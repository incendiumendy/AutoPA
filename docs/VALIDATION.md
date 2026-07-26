# Hardware validation log

Date: 2026-07-26

This file records reproducible acceptance evidence without committing the
printer IP, credentials, USB serial numbers, full configuration backups or raw
datasets.

## Test system

- RatOS with Klipper commit
  `2817b348e23c779b68ae5f27f2b9b9af8cfcf0da`
- Rat Rig V-Core 3 300
- Octopus v1.1 F446 mainboard
- EBB42 Gen2 over USB
- EBB42 onboard LIS2DW configured as `toolboard_t0`
- FLY-ALPS firmware 2.0.0 over a USB hub
- Digital ALPS probe remains connected through EBB42 PA5/PA4

## USB observation

Connecting ALPS directly to the Raspberry Pi had previously coincided with
instability. Moving it to the USB hub restored reliable operation. A later
parallel firmware compile also coincided with an EBB42 disconnect. AutoPA
therefore does not compile or flash firmware during acquisition and treats
USB error/overflow/retransmit changes as a failed run.

## Factory protocol validation

The Mellow USB stream was started with `v\n` and stopped with `uv\n`.
Firmware 2.0.0 returned combined `a=<raw>,b=<filtered>` lines.

Ten-second standalone result:

| Measurement | Result |
| --- | ---: |
| Samples | 25,974 |
| Sample rate | 2,597.43 Hz |
| Raw standard deviation | 5,742.63 counts |
| Filtered standard deviation | 490.12 counts |
| Probe before / after | open / open |
| Klipper after test | ready |

## Combined idle capture

Ten-second synchronized result:

| Measurement | Result |
| --- | ---: |
| Force samples | 25,970 |
| Acceleration samples | 3,880 |
| Acceleration errors / overflows | 0 / 0 |
| Clock pairs | 10 |
| Clock RMS residual | 0.001115 ms |
| Clock maximum residual | 0.002024 ms |
| Aligned rows | 3,853 |
| Probe after test | open |
| Klipper after test | ready |

The mean acceleration-vector magnitude was 9,633.09 mm/s², consistent with an
idle accelerometer dominated by gravity.

## Marker-chain capture

The updated Klipper extra was loaded with a full Klipper service restart.
Live API checks then confirmed:

- `AUTOPA_MARK` and `AUTOPA_VALIDATE` present in `gcode/help`;
- `autopa/events` returned a newly inserted diagnostic marker with exact
  `print_time`;
- `AUTOPA_VALIDATE X_TRAVEL=8 MIN_Z=10` rejected the cold, unhomed printer
  with `AutoPA requires homed X, Y and Z axes`;
- no motion occurred.

The later temperature-aware module version was installed and loaded with a
full Klipper service restart. A call with
`TARGET_TEMP=200 TEMP_TOLERANCE=2` was deliberately made while the printer was
cold and unhomed. It rejected the request at the first safety gate. Klipper
remained ready/standby, the nozzle target remained 0 °C, the toolhead position
remained unchanged and Pressure Advance remained 0.03.

Five-second end-to-end capture:

| Measurement | Result |
| --- | ---: |
| Force samples | 12,986 |
| Acceleration samples | 1,944 |
| Acceleration errors / overflows | 0 / 0 |
| Captured markers | 1 |
| Clock pairs | 5 |
| Clock RMS residual | 0.000213 ms |
| Clock maximum residual | 0.000345 ms |
| Aligned rows | 1,909 |
| Probe after test | open |
| Klipper after test | ready / standby |

## Remaining hardware validation

The acquisition stack is accepted. The following steps are intentionally still
open:

1. inspect the generated smoke-sweep G-code and confirm current PA restore
   value;
2. prepare purge containment and emergency stop;
3. home, park at a safe free-air position and heat the correct filament;
4. run the three-value, three-cycle smoke sweep under supervision;
5. inspect force, acceleration and every marker before trusting an estimate;
6. repeat with a wider/finer grid only if the smoke data are clean;
7. compare AutoPA against a conventional Klipper PA calibration.

## Fail-open validation

The marker handler was changed so missing or internally failed telemetry never
raises a G-code error. After a full Klipper service restart:

- an intentionally empty `AUTOPA_MARK` command returned successfully and was
  skipped;
- a valid `AUTOPA_MARK EVENT=fail_open_test VALUE=continued` returned
  successfully;
- Klipper remained `ready`;
- print state remained `standby`;
- digital probe state remained open/unchanged;
- no movement occurred.

Both stored reference datasets also passed the new analysis quality gates:

| Dataset | Maximum ALPS gap | Maximum LIS2DW gap | Eligible |
| --- | ---: | ---: | --- |
| 10-second idle | 3.668 ms | 2.667 ms | yes |
| 5-second marker chain | 3.303 ms | 2.974 ms | yes |

A synthetic missing-window test is rejected by the same gate. Rejection only
sets `analysis_eligible: false`; it performs no printer action.

## Extruder motion telemetry

The recorder was extended with the read-only Klipper
`motion_report/dump_trapq` endpoint for the active extruder. A three-second idle
capture returned:

| Measurement | Result |
| --- | ---: |
| ALPS force samples | 7,793 |
| LIS2DW acceleration samples | 1,160 |
| Errors / overflows | 0 / 0 |
| Extruder motion segments | 0, expected while idle |

The endpoint subscription completed without Klipper or probe changes. Real
positive-extrusion segments and advisory filament-pressure-loss detection will
be validated during the supervised smoke sweep.

## Temperature and PA status telemetry

The recorder now subscribes read-only to Klipper `extruder` and `print_stats`
status. A three-second idle capture returned ten updates containing:

- nozzle temperature and target;
- current Pressure Advance;
- current Smooth Time;
- print state.

The observed idle values were internally consistent and the capture completed
without errors. Temperature-bound sweep files and the multi-temperature ranking
are covered by synthetic tests; heated hardware validation remains part of the
supervised sweep workflow.

## SUNLU ABS Green 250 °C supervised validation

On 2026-07-26 the printer was homed and parked at X150 Y150 Z30 with the nozzle
in free air. The bed remained off. Tests used SUNLU ABS Green 1.75 mm at a
validated nozzle target of 250 ±2 °C. Every runner used a `finally` cleanup
that set the hotend target to 0 °C and restored Pressure Advance to 0.03.

The first complete three-cycle run
`20260726T151946Z_sunlu_abs_green_250C_final` recorded 51,962 ALPS samples and
7,728 LIS2DW samples without errors or overflows. Its temperature median was
250.00 °C with a 0.92 °C span. The dataset passed acquisition quality, but one
PA 0.01 cycle was below the 3x baseline-MAD signal threshold. AutoPA correctly
withheld a single-run recommendation.

A five-cycle repeat recorded 72,752 force and 10,808 acceleration samples. It
contained one 9.738 ms raw USB arrival gap inside the sweep and was therefore
rejected even though its marker chain was complete. The rejection did not
pause the printer or alter PA.

Two independent timing-clean captures were then pooled with the combined-run
analyzer. Only datasets with `analysis_eligible: true` contributed cycles:

| PA | Included cycles | Normalized cost |
| ---: | ---: | ---: |
| 0.01 | 5 | 1.000000 |
| 0.03 | 5 | 0.604791 |
| 0.05 | 3 | 0.177567 |

The resulting experimental recommendation is PA 0.05 with a 0.427224 cost gap
to the second-ranked value. `apply_automatically` remained `false`; the live
printer was verified at PA 0.03, hotend target 0 °C, Klipper ready and print
state standby. A conventional printed PA pattern is still required before
saving 0.05 to a filament or printer profile.

## Optional accelerometer validation

The recorder accepts `lis2dw`, `lis3dh`, `adxl345`, `mpu9250` and `none`.
Driver endpoints are selected explicitly; no fallback sensor is guessed.

A five-second live `none` capture on the same Raspberry Pi recorded 12,987
ALPS samples, zero acceleration samples and zero recorder errors. Alignment
used the regularized force timebase and produced 12,987 combined rows.
Acceleration-specific quality gates were skipped, the final dataset had no
warnings and `analysis_eligible` was true. The dashboard reported the optional
accelerometer as disabled and healthy. The existing EBB42 LIS2DW path remains
the installed default and was not reconfigured.
