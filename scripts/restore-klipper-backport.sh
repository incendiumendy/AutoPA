#!/bin/sh
set -eu

KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
BACKUP="${1:-}"

[ -n "$BACKUP" ] || {
    printf '%s\n' "Usage: $0 /absolute/path/to/.autopa-backup/TIMESTAMP" >&2
    exit 1
}
[ -d "$BACKUP/klippy/extras" ] && [ -d "$BACKUP/src" ] || {
    printf '%s\n' "Invalid AutoPA backup: $BACKUP" >&2
    exit 1
}
case "$BACKUP" in
    "$KLIPPER_DIR"/.autopa-backup/*) ;;
    *)
        printf '%s\n' "Backup is outside $KLIPPER_DIR/.autopa-backup" >&2
        exit 1
        ;;
esac

cp -p "$BACKUP/klippy/extras/load_cell.py" \
    "$KLIPPER_DIR/klippy/extras/load_cell.py"
cp -p "$BACKUP/src/Kconfig" "$KLIPPER_DIR/src/Kconfig"
cp -p "$BACKUP/src/Makefile" "$KLIPPER_DIR/src/Makefile"
rm -f \
    "$KLIPPER_DIR/klippy/extras/ads131m0x.py" \
    "$KLIPPER_DIR/klippy/extras/static_pwm_clock.py" \
    "$KLIPPER_DIR/klippy/extras/autopa_capture.py" \
    "$KLIPPER_DIR/src/sensor_ads131m0x.c"

printf '%s\n' "Restored Klipper files from $BACKUP"
printf '%s\n' "Klipper was not restarted and no MCU was flashed."
