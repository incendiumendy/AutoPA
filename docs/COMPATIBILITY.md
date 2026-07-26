# Compatibility contract: Klipper and RatOS

## Principle

AutoPA is a Klipper/Moonraker extension. RatOS is treated as a supported
distribution, not as a firmware fork. Distribution-owned configuration is
never replaced or patched in place.

## Shared architecture

| Component | Generic Klipper | RatOS |
| --- | --- | --- |
| ALPS force source | Factory USB CDC protocol | Same |
| Existing Z probe | Existing digital `[probe]` | Same |
| Acceleration | Optional LIS2DW/LIS3DH/ADXL345/MPU9250 | Same |
| Time mapping | `autopa/clock` endpoint | Same |
| PA command | `SET_PRESSURE_ADVANCE` | Same |
| Test markers | `AUTOPA_MARK` | Same |
| Safety gate | `AUTOPA_VALIDATE` | Same |
| Updates | Separate Moonraker entry | Separate Moonraker entry |

## Rules

1. The host paths have environment overrides:
   `KLIPPER_DIR` and `PRINTER_CONFIG_DIR`.
2. The default installer links one AutoPA extra and creates one separate
   `autopa.cfg`; it does not edit `printer.cfg`.
3. `--enable-config` is an explicit opt-in that backs up `printer.cfg` before
   appending one idempotent include.
4. RatOS macros, generated files and configurator hooks remain untouched.
5. Acquisition uses Klipper's API socket and the stable ALPS
   `/dev/serial/by-id` path, not hard-coded `ttyACM` numbers.
6. No install or update command flashes ALPS, EBB42 or the mainboard.
7. The Moonraker update entry manages only the AutoPA checkout. It may restart
   Klipper to load the linked extra but may not update Klipper, Moonraker or
   RatOS.
8. Printer-specific paths, serial IDs, IP addresses, credentials, backups and
   datasets are not committed.

## Moonraker update manager

Use `config/moonraker-autopa.conf.example` only after a real GitHub repository
exists and the `origin` and `path` values match the installed checkout.

The initial development channel is `dev`. A future `stable` channel requires
versioned releases and repeated hardware validation. Moonraker requires a
clean Git checkout; local changes must be reported rather than overwritten.

## Acceptance criteria

- RatOS and generic Klipper reach `ready` after installation.
- The existing digital probe state is unchanged before and after capture.
- ALPS and the selected optional accelerometer contain samples with no
  reported overflow; force-only mode is explicitly recorded as disabled.
- Installation creates a recoverable backup before a config edit.
- Uninstallation removes only the project-owned symlink.
- AutoPA appears independently in the Moonraker update manager.
- An AutoPA update never starts a sweep or applies a PA value.
