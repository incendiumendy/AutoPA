# Third-party notices

AutoPA is an independent implementation and is not a fork of any project
listed below.

## Research inspirations

The following projects inspired AutoPA's problem statement, experimental
direction and comparison of pressure-advance analysis methods. Their source
files are not vendored in AutoPA:

- [CNCKitchen/PrusaPATuner](https://github.com/CNCKitchen/PrusaPATuner)
  (AGPL-3.0): inspiration for load-cell-based PA calibration and analysis
  research on Prusa Buddy firmware.
- [vzagranichnyy/KAPAT](https://github.com/vzagranichnyy/KAPAT)
  (AGPL-3.0): inspiration and comparison point for a Klipper experiment using
  a Mellow ALPS load cell.

## Klipper-derived backport material

AutoPA contains selected Klipper-derived GPLv3 backport material needed to
evaluate ADS131M0x support on the verified RatOS Klipper revision:

- `backport/klipper/klippy/extras/ads131m0x.py`
- `backport/klipper/klippy/extras/static_pwm_clock.py`
- `backport/klipper/src/sensor_ads131m0x.c`
- `backport/klipper/core-2817b348.patch`
- `deploy/ratos3-printer-autopa.patch`

The original copyright and GPLv3 notices in those source files are retained.
Upstream project and development context:

- [Klipper3d/klipper](https://github.com/Klipper3d/klipper)
- [FLY-ALPS / ADS131M02 development thread](https://klipper.discourse.group/t/strain-gauge-load-cell-based-endstops/2134/622)

AutoPA as a whole is distributed under GPL-3.0-or-later as declared in
`pyproject.toml` and the repository `LICENSE`.
