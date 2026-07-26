# FLY-ALPS firmware

## Verified Klipper build settings

The configuration in `firmware/fly-alps-klipper.config` reproduces the settings
published by the author of Klipper's ADS131M0x support:

- STMicroelectronics STM32
- STM32F072
- 8 KiB bootloader
- 8 MHz crystal
- USB on PA11/PA12
- GPIO at startup: `!PC13`

It is intended for Klipper after Katapult has been installed. The 8 KiB offset
must not be used when directly replacing the factory firmware without
Katapult.

## Verified Katapult settings

- STMicroelectronics STM32
- STM32F072
- normal Katapult build, not the deployment application
- 8 MHz crystal
- USB on PA11/PA12
- application start offset: 8 KiB
- rapid double-click reset entry enabled

The first Katapult installation changes the board's recovery/update path and is
therefore kept separate from the host backport installation. Before doing it,
the factory firmware and Mellow web recovery instructions must be available.

## Build

From the matching, patched Klipper tree:

```sh
make clean KCONFIG_CONFIG=config.fly-alps
make olddefconfig KCONFIG_CONFIG=config.fly-alps
make KCONFIG_CONFIG=config.fly-alps
```

Copy `firmware/fly-alps-klipper.config` to `config.fly-alps` first. The build
must report `CONFIG_WANT_ADS131M0X=y`; otherwise the image is rejected.

Building is safe and does not communicate with the board. Flashing is a
separate operation.
