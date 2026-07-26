#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
KLIPPER_DIR=${KLIPPER_DIR:-"$HOME/klipper"}
TARGET_MODULE="$KLIPPER_DIR/klippy/extras/autopa_clock.py"
EXPECTED_MODULE="$PROJECT_DIR/klipper/extras/autopa_clock.py"

if [ -L "$TARGET_MODULE" ]; then
    LINK_TARGET=$(readlink "$TARGET_MODULE")
    if [ "$LINK_TARGET" = "$EXPECTED_MODULE" ]; then
        rm -- "$TARGET_MODULE"
        printf '%s\n' "Removed AutoPA Klipper module symlink."
    else
        printf '%s\n' "Refusing to remove unrelated symlink: $TARGET_MODULE" >&2
        exit 1
    fi
elif [ -e "$TARGET_MODULE" ]; then
    printf '%s\n' "Refusing to remove a non-symlink module: $TARGET_MODULE" >&2
    exit 1
else
    printf '%s\n' "AutoPA Klipper module is already absent."
fi

printf '%s\n' "The config include and measurement data were kept."
printf '%s\n' "Remove [include autopa.cfg] manually, then restart Klipper."
