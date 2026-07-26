# Local live dashboard

AutoPA includes a local dashboard for RatOS and generic Klipper/Moonraker
installations. It is served by the Raspberry Pi and is intentionally not
published as a public control surface.

## What it shows

- Klipper/Moonraker connection and print state;
- nozzle temperature, requested temperature, Pressure Advance and Smooth Time;
- configured nozzle diameter, filament diameter and maximum extrusion
  cross-section from Klipper's active `[extruder]` configuration;
- live FLY-ALPS filtered force while an AutoPA recording is active;
- live vector magnitude from the selected optional LIS2DW, LIS3DH, ADXL345 or
  MPU9250 while an AutoPA recording is active;
- actual force and acceleration sample rates;
- synchronized-capture state and latest dataset;
- a single overall `OK`, `waiting`, `warning` or `error` state.

An idle sensor is shown as `waiting`, not as a hardware failure. An explicitly
disabled optional accelerometer is shown as healthy and disabled. A recording
that stops updating for more than two seconds is a warning.

The nozzle values are read-only machine facts. Change them in Klipper's
`[extruder]` configuration, not in AutoPA. AutoPA uses them to document the
test setup and to keep later volumetric-flow checks reproducible.

## Material profiles

The first version includes editable PLA, PETG, ABS, ASA and TPU profiles. Each
profile stores:

- minimum, maximum and step temperature;
- minimum and maximum bed temperature;
- minimum and maximum print speed;
- PA start, stop and step;
- number of test cycles.

Profiles are browser-local preferences. They do not alter the slicer, heat the
printer or apply Pressure Advance. The values are starting ranges only and must
stay inside the filament manufacturer's specification.

Custom profiles can be added with `+ Profil`, freely named, annotated with a
manufacturer/note and removed again. Existing v2 browser profiles are migrated
to the ID-based v3 format on first load.

## Live indicators

Each chart footer has its own status point:

- green `Live` means that channel is currently receiving fresh data;
- `Kein Live-Stream` means the displayed value is from the latest completed
  capture;
- an intentionally disabled accelerometer is labeled `Deaktiviert`;
- hotend temperature is live whenever Moonraker is connected.

The word `Live` is therefore never shown for stale ALPS or acceleration data.

## Data path

The recorder remains the only process that opens the FLY-ALPS serial port. At
most ten times per second it atomically replaces:

```text
~/printer_data/autopa/live.json
```

The dashboard reads that small file and Moonraker's read-only object status.
It never opens the sensor serial port and therefore cannot compete with a
measurement.

The atomic file write runs in a dedicated 10 Hz publisher thread. The ALPS
reader only updates an in-memory snapshot and never performs dashboard file
I/O, preserving the high-rate serial timing.

## Build and install

Build the browser assets on a development machine with Node.js 22 or newer:

```sh
cd dashboard
npm ci
npm test
```

The build exports a static `dashboard/dist/client/index.html` plus hashed
assets. These files are retained in the repository so the Raspberry Pi does
not need Node.js.

On the Raspberry Pi:

```sh
cd ~/AutoPA
sh scripts/install-dashboard.sh
```

Then open:

```text
http://<printer-ip>:7126/
```

## Mainsail/RatOS navigation

`scripts/install-mainsail-integration.sh` adds an `AutoPA` entry to RatOS'
custom Mainsail navigation and exposes the dashboard through the same web
server:

```sh
cd ~/AutoPA
sh scripts/install-mainsail-integration.sh
```

After installation use:

```text
http://<printer-ip>/autopa/
```

Mainsail custom navigation does not provide a stable embedded right-hand
iframe surface. AutoPA therefore opens as its own page and includes a
`Zurück zu Mainsail` button. The button also removes the direct development
port `7126` when the dashboard was opened through that address.

The installer backs up the active navigation and Nginx site, validates the
resulting JSON and runs `nginx -t` before reloading Nginx. It does not modify
Klipper configuration or restart Klipper.

The generated system service uses filesystem hardening, runs without extra
privileges and exposes only `GET /api/status` and `GET /api/health`. Every POST
request is rejected with HTTP 405 and `printer_action: none`.

## Security boundary

Port 7126 is intended only for the trusted printer LAN. Do not expose it
directly to the internet. Authentication and reverse-proxy integration are not
part of the initial read-only version.
