# Preferred installation: Mellow factory firmware

This mode reads ALPS samples over its existing USB CDC interface and leaves the
digital probe firmware intact.

## Components

- `src/autopa/alps_serial.py`: standalone ALPS protocol reader.
- `src/autopa/sync_recorder.py`: combined ALPS + LIS2DW dataset recorder.
- `klipper/extras/autopa_clock.py`: clock mapping, exact markers and a
  read-only safety validator.
- `config/autopa-capture.cfg.example`: Klipper include example.

## Installation outline

1. Copy the project to a dedicated directory, for example
   `~/printer_data/autopa-project`.
2. Copy or symlink `klipper/extras/autopa_clock.py` into
   `~/klipper/klippy/extras/autopa_clock.py`.
3. Add `[autopa_clock]` through a separate included configuration file.
4. Run `RESTART` while the printer is idle. No MCU firmware is changed.
5. Confirm that `autopa/clock` and `lis2dw/dump_lis2dw` are available.
6. Run the idle capture below.

The installer creates a timestamped backup and links only the AutoPA Klipper
module. By default it does not edit `printer.cfg`:

```sh
./scripts/install.sh
```

To add the separate include idempotently during an explicitly requested
installation:

```sh
./scripts/install.sh --enable-config
```

It never changes RatOS-owned configuration fragments or MCU firmware.

On a first installation, `RESTART` is sufficient when the module has never been
imported. After updating an existing `autopa_clock.py`, restart the Klipper
system service so Python imports the new code. Moonraker's `managed_services:
klipper` performs that restart for Update Manager updates.

## First idle capture

```sh
cd ~/printer_data/autopa-project
PYTHONPATH=src python3 -m autopa.sync_recorder \
  --alps-device /dev/serial/by-id/usb-STMicroelectronics_PressureLeveling_YOUR_ID-if00 \
  --duration 10 \
  --name idle_10s
```

Expected files are `force.csv`, `acceleration.csv`,
`acceleration_batches.csv`, `clock_sync.csv`, `events.csv` and
`manifest.json`.

Acceptance criteria:

- both sample counts are greater than zero;
- ALPS start/stop returns without disconnecting USB;
- acceleration error and overflow counters remain zero;
- EBB42, Octopus and ALPS remain visible;
- `QUERY_PROBE` has the same state before and after capture;
- a hand tap changes both ALPS values and the digital probe state;
- no Z movement is performed in this phase.

## Time alignment

ALPS samples are stamped with Linux monotonic time. LIS2DW samples already use
Klipper `print_time`. Once per second the recorder queries `autopa/clock`; those
pairs are stored in `clock_sync.csv` and are used to transform ALPS timestamps
into `print_time` during analysis.

The raw files are immutable evidence. Resampling and filtering produce new
derived files rather than rewriting the originals.

## Moonraker update manager

`config/moonraker-autopa.conf.example` provides the update-manager section.
It can only be enabled after the project has a real GitHub origin and has been
cloned to the configured path. Replace `OWNER` and the path first.

AutoPA appears as its own entry. Its updater manages only this Git repository
and restarts Klipper so a changed extra module is loaded. It does not update
RatOS, Moonraker, Klipper itself or any MCU firmware.

## Rollback

Run `./scripts/uninstall.sh`, remove `[include autopa.cfg]`, then issue
`RESTART`. The uninstaller removes only a symlink that points back to this
project; it keeps configuration and measurement data. The Mellow firmware,
EBB42 firmware and probing wiring were never changed.
