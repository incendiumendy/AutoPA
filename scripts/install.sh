#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
KLIPPER_DIR=${KLIPPER_DIR:-"$HOME/klipper"}
PRINTER_CONFIG_DIR=${PRINTER_CONFIG_DIR:-"$HOME/printer_data/config"}
ENABLE_CONFIG=0

if [ "${1:-}" = "--enable-config" ]; then
    ENABLE_CONFIG=1
elif [ "$#" -ne 0 ]; then
    printf '%s\n' "Usage: $0 [--enable-config]" >&2
    exit 2
fi

SOURCE_MODULE="$PROJECT_DIR/klipper/extras/autopa_clock.py"
TARGET_MODULE="$KLIPPER_DIR/klippy/extras/autopa_clock.py"
SOURCE_CONFIG="$PROJECT_DIR/config/autopa.cfg"
TARGET_CONFIG="$PRINTER_CONFIG_DIR/autopa.cfg"
PRINTER_CONFIG="$PRINTER_CONFIG_DIR/printer.cfg"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_DIR="$PRINTER_CONFIG_DIR/.autopa-backup/$STAMP"

[ -f "$SOURCE_MODULE" ] || {
    printf '%s\n' "Missing source module: $SOURCE_MODULE" >&2
    exit 1
}
[ -d "$KLIPPER_DIR/klippy/extras" ] || {
    printf '%s\n' "Klipper extras directory not found: $KLIPPER_DIR" >&2
    exit 1
}
[ -d "$PRINTER_CONFIG_DIR" ] || {
    printf '%s\n' "Printer config directory not found: $PRINTER_CONFIG_DIR" >&2
    exit 1
}

mkdir -p "$BACKUP_DIR"
if [ -e "$TARGET_MODULE" ] || [ -L "$TARGET_MODULE" ]; then
    cp -pL "$TARGET_MODULE" "$BACKUP_DIR/autopa_clock.py"
fi
if [ -f "$TARGET_CONFIG" ]; then
    cp -p "$TARGET_CONFIG" "$BACKUP_DIR/autopa.cfg"
fi
if [ "$ENABLE_CONFIG" -eq 1 ] && [ -f "$PRINTER_CONFIG" ]; then
    cp -p "$PRINTER_CONFIG" "$BACKUP_DIR/printer.cfg"
fi

ln -sfn "$SOURCE_MODULE" "$TARGET_MODULE"
if [ ! -f "$TARGET_CONFIG" ]; then
    cp -p "$SOURCE_CONFIG" "$TARGET_CONFIG"
fi

if [ "$ENABLE_CONFIG" -eq 1 ]; then
    [ -f "$PRINTER_CONFIG" ] || {
        printf '%s\n' "printer.cfg not found: $PRINTER_CONFIG" >&2
        exit 1
    }
    TEMP_CONFIG=$(mktemp "$PRINTER_CONFIG.autopa.XXXXXX")
    trap 'rm -f "$TEMP_CONFIG"' EXIT HUP INT TERM
    awk '
        BEGIN { inserted = 0 }
        /^[[:space:]]*\[include[[:space:]]+autopa\.cfg\][[:space:]]*$/ {
            next
        }
        /^#\*# <[-]+ SAVE_CONFIG [-]+>$/ && !inserted {
            print ""
            print "[include autopa.cfg]"
            print ""
            inserted = 1
        }
        { print }
        END {
            if (!inserted) {
                print ""
                print "[include autopa.cfg]"
            }
        }
    ' "$PRINTER_CONFIG" > "$TEMP_CONFIG"
    chmod 0644 "$TEMP_CONFIG"
    mv "$TEMP_CONFIG" "$PRINTER_CONFIG"
    trap - EXIT HUP INT TERM
fi

printf '%s\n' "AutoPA module installed: $TARGET_MODULE"
printf '%s\n' "AutoPA config available: $TARGET_CONFIG"
printf '%s\n' "Backup created: $BACKUP_DIR"
if [ "$ENABLE_CONFIG" -eq 0 ]; then
    printf '%s\n' "Add this line to printer.cfg when ready:"
    printf '%s\n' "[include autopa.cfg]"
fi
printf '%s\n' "Run RESTART (or restart the Klipper service) while idle."
