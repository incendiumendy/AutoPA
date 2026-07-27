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
- learned no-flow baseline, relative nozzle load in ALPS counts and normalized
  pressure;
- dry-run PA and firmware-retraction recommendations with evidence counters;
- optional material-profile chamber-filter rules with filename token,
  validated `fan_generic`, speed and post-run;
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

## Clickable live data and print-bound recorder manager

The dashboard's `Live-Daten einschalten` button can start a passive synchronized
recording while the printer is idle or while Klipper already reports
`printing`. The managed recording:

- immediately supplies fresh FLY-ALPS and optional accelerometer values;
- attaches to the current print without restarting Klipper or Moonraker;
- automatically attaches when a new print begins during a live preview;
- records FLY-ALPS, the selected optional accelerometer, Klipper motion,
  temperature, Pressure Advance and G-code context;
- continues when the browser is closed;
- stops cleanly when `print_stats.state` reaches `complete`, `cancelled`,
  `error` or `standby`;
- can be switched off manually from the dashboard at any time;
- has a twelve-hour hard duration limit.

Starting or stopping a recording sends no G-code and never pauses or cancels
the print. A temporary Moonraker-monitor failure leaves the recording running;
the duration limit remains the final bound. Recorder failures stop only the
measurement.

The generated systemd unit grants write access only to
`~/printer_data/autopa`. `ProtectHome=read-only` and the remaining service
hardening stay active.

## Native movable Mainsail tile

An optional pinned-source Mainsail integration provides a real dashboard panel
that can be moved, hidden and collapsed through Mainsail's normal dashboard
settings. It shows the compact AutoPA state, G-code context, executed speed and
volumetric flow and permits only `off`/`dry_run` switching.

It does not modify RatOS Theme or `navi.json`, and it cannot arm printer
commands. See the bilingual
[native Mainsail tile guide](MAINSAIL_TILE.md).

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

The generated system service uses filesystem hardening and runs without extra
privileges. Status endpoints remain read-only. The narrowly scoped control
endpoints can only configure dry-run, request transient arming or disarm the
controller. The shipped service has
`AUTOPA_ALLOW_PRINTER_COMMANDS=0`, so arming is rejected server-side even if a
browser calls the endpoint directly.

Chamber-filter commands use an independent
`AUTOPA_ALLOW_FILTER_COMMANDS=0` lock. Saving a material profile does not
implicitly unlock it. Only validated `SET_FAN_SPEED` calls for a real
`fan_generic` can pass that separate path. See
[filename-triggered chamber filter](CHAMBER_FILTER.md).

For the first printer validation, keep that value at `0`. The pressure gauge
and proposed PA/retraction values are still visible during an active capture.
Only after the dry-run evidence has been reviewed may an operator deliberately
set it to `1`, restart only the AutoPA dashboard service and enter the exact
phrase `AUTOPA VALIDIEREN`. See
[adaptive PA and Auto-Retract](ADAPTIVE_CONTROL.md).

## Security boundary

Port 7126 is intended only for the trusted printer LAN. Do not expose it
directly to the internet. Authentication and reverse-proxy integration are not
part of this experimental validation surface.
