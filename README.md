# AutoPA for Mellow FLY-ALPS and Klipper

AutoPA records nozzle-force data from a Mellow FLY-ALPS together with real
toolhead acceleration from the LIS2DW on an EBB42 Gen2. The streams are aligned
on Klipper's `print_time` clock and will be used for a supervised,
sensor-assisted Pressure Advance sweep.

An optional local dashboard displays live force, movement, temperature,
Pressure Advance, measurement health and editable PLA/ABS/PETG/ASA/TPU test
profiles. It remains read-only toward the printer. See
[local live dashboard](docs/DASHBOARD.md).

The project targets both ordinary Klipper/Moonraker installations and RatOS.
It does not replace RatOS configuration files.

> Status: experimental development project. Acquisition and clock alignment
> are validated on one RatOS printer. Automatic PA recommendations are not yet
> validated and must not be applied unattended.

## Validated hardware

- Rat Rig V-Core 3 300 with RatOS
- Mellow FLY-ALPS firmware `2.0.0`, USB through a powered/stable hub
- BTT EBB42 Gen2 over USB
- EBB42 onboard LIS2DW as `lis2dw toolboard_t0`
- Existing digital ALPS probe on EBB42 pins PA5 (enable) and PA4 (trigger)

## Preferred architecture

```text
Raspberry Pi / RatOS or Klipper
|- USB hub -> Mellow FLY-ALPS factory firmware
|             |- USB CDC force stream (~2.6 kHz)
|             `- digital trigger remains connected to the EBB42
`- USB -> EBB42 Gen2
              |- normal toolboard functions
              `- LIS2DW acceleration stream (~386 Hz)
```

The EBB42 is a USB device, not a USB host or hub. The ALPS therefore needs its
own USB connection to the Pi or to a good powered hub. Do not crimp a passive
USB connection from the ALPS into the EBB42 USB connector.

The direct ALPS-to-Pi connection was unstable on the validated machine. A USB
hub restored reliable operation. See [USB stability](docs/USB_STABILITY.md).

## Why the ALPS is not flashed

The public Mellow firmware exposes force samples over USB while its digital
probe output continues to work. This was verified before and after a combined
ten-second ALPS/LIS2DW capture.

Flashing Klipper onto the ALPS would remove the factory digital-probe behavior.
That path is retained only as an experimental reference under `firmware/`,
`backport/` and `config/ALPS-load-cell.cfg.example`. It must not be used until a
complete and independently validated `load_cell_probe` replacement or another
Z probe exists.

## Current validated result

The first combined idle dataset produced:

| Check | Result |
| --- | ---: |
| ALPS firmware | 2.0.0 |
| ALPS force samples | 25,970 in 10 s |
| ALPS sample rate | 2,596.98 Hz |
| LIS2DW acceleration samples | 3,880 in about 10 s |
| LIS2DW sample rate | 385.87 Hz |
| LIS2DW errors / overflows | 0 / 0 |
| Clock-fit RMS residual | 0.0011 ms |
| Clock-fit maximum residual | 0.0021 ms |
| Derived aligned rows | 3,853 |
| Digital probe state | unchanged |

A second five-second run validated the complete marker path:

- 12,986 force samples and 1,944 acceleration samples;
- zero errors and zero overflows;
- one `AUTOPA_MARK` event preserved in `events.csv`;
- clock-fit maximum residual 0.00035 ms;
- Klipper remained ready/standby and the probe state remained unchanged.

Raw machine datasets and printer backups are intentionally excluded from Git.

## Repository layout

```text
src/autopa/
  alps_serial.py     Mellow USB protocol reader
  sync_recorder.py   simultaneous ALPS/LIS2DW recorder
  align.py           monotonic-time to Klipper print-time alignment
  diagnose.py        non-moving live endpoint and safety checks
  calibration.py     per-machine multi-point force calibration
  filament.py        advisory lost-extrusion-pressure detection
  material.py        filament consistency and temperature comparison
  temperature_plan.py safe per-temperature sweep file generator
  dashboard.py       read-only local status and static dashboard server
  quality.py         acquisition and idle-baseline diagnostics
  sweep.py           bounded Klipper PA sweep generator
klipper/extras/
  autopa_clock.py    clock endpoint, exact G-code markers and safety check
config/
  autopa.cfg         minimal Klipper include
docs/                installation, protocol, compatibility and safety notes
tests/               dependency-free unit tests
dashboard/           responsive browser interface and static production build
```

## Install the safe factory-firmware mode

The only Klipper-side component required for this mode is
`klipper/extras/autopa_clock.py`. It:

- reports the Linux-monotonic/Klipper-print-time mapping;
- records exact `AUTOPA_MARK` boundaries;
- provides `AUTOPA_VALIDATE` to check homing, Z clearance, X travel and hotend
  extrusion readiness;
- optionally verifies that the requested nozzle target and measured
  temperature match the temperature-bound sweep within a configured
  tolerance.

It does not read or change the probe, move an axis, change PA, or flash an MCU.
See [factory-mode installation](docs/INSTALL_FACTORY_MODE.md).

After changing an already imported Klipper Python extra, use a real Klipper
service restart. A G-code `RESTART` reloads configuration but keeps imported
Python modules cached in the same process.

## Capture and align

On the Raspberry Pi:

```sh
cd ~/printer_data/autopa-project
PYTHONPATH=src python3 -m autopa.sync_recorder \
  --alps-device /dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_YOUR_ID-if00 \
  --accelerometer-type lis2dw \
  --accelerometer toolboard_t0 \
  --duration 10 \
  --name idle_10s

PYTHONPATH=src python3 -m autopa.align \
  ~/printer_data/autopa/<dataset>

PYTHONPATH=src python3 -m autopa.quality \
  ~/printer_data/autopa/<dataset>

PYTHONPATH=src python3 -m autopa.analyze \
  ~/printer_data/autopa/<dataset>
```

The recorder writes raw force, acceleration, batch diagnostics, clock pairs,
G-code events and a manifest. Alignment and quality analysis create new
derived files and never rewrite the raw evidence.

The motion channel is optional. AutoPA supports Klipper's LIS2DW, LIS3DH,
ADXL345 and MPU9250 data endpoints; use `--accelerometer-type none` for a
force-only capture. See
[optional accelerometers](docs/ACCELEROMETERS.md).

Repeated quality-approved runs can be pooled without admitting rejected data:

```sh
PYTHONPATH=src python3 -m autopa.analyze \
  ~/printer_data/autopa/<dataset-1> \
  ~/printer_data/autopa/<dataset-2> \
  --output ~/printer_data/autopa/combined-analysis.json
```

Each PA value still requires at least three included cycles. The result remains
experimental and always sets `apply_automatically` to `false`.

Different ALPS boards and hotend mechanics can use an optional multi-point
calibration for offset, polarity and counts-to-force conversion. PA metrics
remain locally normalized even without it. See
[per-machine calibration](docs/CALIBRATION.md).

## Generate a supervised smoke sweep

First obtain the current PA value from Klipper. It is mandatory as
`--restore-advance`, so the generated file restores that value at the end.

```sh
PYTHONPATH=src python3 -m autopa.sweep \
  --k-start 0.01 \
  --k-stop 0.05 \
  --k-step 0.02 \
  --cycles 3 \
  --restore-advance 0.03 \
  --output autopa-smoke.gcode
```

The example assumes the printer's current value is `0.03`; always replace
`--restore-advance` with the value reported by your own printer. It uses
25.2 mm of filament and takes about 11.25 seconds, excluding acceleration and
command overhead. Every cycle:

1. moves X by +8 mm over one second while extruding slowly;
2. returns X by -8 mm over 0.25 seconds while extruding quickly;
3. ends at exactly the starting X coordinate.

The X component is required because the validated Klipper version only enables
Pressure Advance for positive extrusion moves with X or Y motion. It also gives
the LIS2DW a real movement signal for rejecting mechanical artifacts.

Before any sweep:

- home X/Y/Z;
- move the nozzle into free air, at least 10 mm above the bed;
- heat the loaded filament to a safe extrusion temperature;
- place a purge container below the nozzle;
- verify the requested +X travel remains inside the build area;
- remain at the printer with emergency stop available;
- start the recorder before executing the generated G-code.

`AUTOPA_VALIDATE` rejects the file if axes are not homed, Z is too low, the +X
move would exceed the axis limit, or the hotend is too cold.

## Project boundaries

- Normal printing is fail-open: recording or sensor failures never pause,
  cancel or emergency-stop a print.
- Analysis is fail-closed: missing, delayed, clipped or implausible data
  suppresses the PA recommendation.
- Recording never changes PA automatically.
- Analysis will first return a recommendation with confidence and per-cycle
  evidence.
- Applying a recommendation remains a separate user-confirmed action.
- Normal probing stays on the factory digital ALPS signal.
- `TEST_RESONANCES` is not run during printing; AutoPA only passively records
  LIS2DW samples.
- A project update may update only AutoPA files and its own service. It must not
  update RatOS, Klipper, Moonraker or MCU firmware.

The complete policy and current quality thresholds are documented in
[fail-open printing](docs/FAIL_OPEN.md).

AutoPA can also compare commanded Klipper extrusion with measured nozzle
pressure. A sustained pressure collapse can indicate broken, empty or stripped
filament, but remains advisory and cannot identify the exact cause without an
additional filament switch or motion encoder. See
[filament pressure-loss detection](docs/FILAMENT_MONITOR.md).

Temperature-dependent PA behavior can be compared across at least three stable
test temperatures. The result is an experimental sensor-derived process
window, not a substitute for stringing, degradation and layer-adhesion tests.
See [material and temperature characterization](docs/MATERIAL_TEMPERATURE.md).

## References and attribution

AutoPA is an independent implementation with its own Git history. It is **not
a fork** of PrusaPATuner, KAPAT, Klipper or RatOS. PrusaPATuner and KAPAT are
linked below as research and comparison projects; their source files are not
vendored in AutoPA.

The test shape and planned analysis compare step response, phase lag and
integral area, inspired by the research in
[CNCKitchen/PrusaPATuner](https://github.com/CNCKitchen/PrusaPATuner).
PrusaPATuner targets Buddy firmware and is not copied into this project;
Klipper uses different commands, timing and acquisition paths.

The files below `backport/klipper/` include GPLv3-licensed Klipper-derived
backport material with the upstream copyright headers retained. See
[Third-party notices](THIRD_PARTY_NOTICES.md) for the exact scope and links.

- [Mellow FLY-ALPS web tool](https://mellow.klipper.cn/en/docs/ToolsDoc/fly-alps-tool/)
- [Klipper Pressure Advance](https://www.klipper3d.org/Pressure_Advance.html)
- [Klipper resonance measurement and LIS2DW](https://www.klipper3d.org/Measuring_Resonances.html)
- [Klipper G-code command reference](https://www.klipper3d.org/G-Codes.html)
- [KAPAT Klipper experiment](https://github.com/vzagranichnyy/KAPAT)
- [FLY-ALPS / ADS131M02 development thread](https://klipper.discourse.group/t/strain-gauge-load-cell-based-endstops/2134/622)
