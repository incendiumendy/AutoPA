# RatOS 2.1.2: ALPS raw-load-cell backport

## Status

The installed printer uses RatOS 2.1.2 with its Klipper fork at commit
`2817b348`. That version already contains Klipper's generic bulk-sensor and
`[load_cell]` framework, but does **not** include the ADS131M0x driver needed
by the FLY-ALPS board. It also does not contain the newer `trigger_analog`
infrastructure.

For automatic pressure-advance measurement, the required first milestone is
the raw measurement path plus a timestamped force-data endpoint. It does not
require `trigger_analog` and does not replace the installed digital ALPS probe
configuration on the host. The endpoint allows force data to be correlated
with the LIS2DW accelerometer already installed on the EBB42 Gen2.

Important: flashing Klipper onto the ALPS replaces Mellow's firmware and its
digital probe output. The currently configured EBB42 `PA4`/`PA5` probe path
will then no longer provide bed probing. This raw-only milestone must not be
flashed on a printer that depends on ALPS for Z homing. Deployment requires
either the complete Klipper `load_cell_probe`/`trigger_analog` path or an
independent, tested Z probe.

## Scope of the first backport

The minimal patch must add the upstream ADS131M0x implementation at both ends:

1. Host: `klippy/extras/ads131m0x.py`, add `ads131m0x` to the sensor map in
   `klippy/extras/load_cell.py`, and expose timestamped force batches for the
   synchronized recorder.
2. MCU: `src/sensor_ads131m0x.c`, its `Makefile` entry, and an
   `WANT_ADS131M0X` Kconfig option. The feature must also select sensor-bulk
   support.
3. The host and ALPS MCU firmware are deployed as one matched pair.

The load-cell-probe / MCU-trigger path is a separate second backport milestone.
It replaces a safety-critical probing path and requires the substantially
larger `trigger_analog` stack. Until that milestone passes tests, the ALPS
stays on Mellow firmware and the existing RatOS `[probe]` remains active.

## Rules for deployment

- Apply only to the verified RatOS Klipper commit above.
- Create a git branch and a full `/home/pi/klipper` backup before applying.
- Stop Klipper before rebuilding/restarting it; do not use a blind third-party
  installer.
- Build the ALPS firmware with the exact same source revision.
- Do not flash the raw-only firmware while ALPS is the only Z probe.
- First prove that Klipper starts with the new module but without an active
  `[load_cell]` section. Then add the section and validate streaming data.
- Keep the original Mellow firmware image/recovery procedure available before
  flashing the ALPS MCU.
- Revalidate the patch after every RatOS/Klipper update. RatOS updates may
  replace the patched files.

## Why KAPAT is not installed directly

KAPAT is useful as a reference and later as the PA analysis UI, but its current
installer copies files directly into `~/klipper/klippy/extras` and restarts
Klipper. That is unsafe on a managed RatOS installation and it does not ship
the ADS131M0x module that FLY-ALPS needs. This project will instead use an
explicit, reviewable patch and a separate KAPAT integration step.

## Evidence captured during preparation

- RatOS Klipper exposes `bulk_sensor`, `ads1220`, `hx71x`, and `[load_cell]`.
- Its source tree has no `ads131m0x`, `load_cell_probe`, or `trigger_analog`.
- Upstream Klipper's ADS131M0x driver is based on the already-present bulk
  sensor interface, so raw-data integration has a bounded change set.
- The existing `lis2dw toolboard_t0` responds to a live
  `ACCELEROMETER_QUERY`; no additional accelerometer wiring is required.
