#!/bin/sh
set -eu

EXPECTED_COMMIT="2817b348e23c779b68ae5f27f2b9b9af8cfcf0da"
MODE="${1:---check}"
KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PAYLOAD="$PROJECT_DIR/backport/klipper"
CAPTURE_MODULE="$PROJECT_DIR/klipper/extras/autopa_capture.py"

fail() {
    printf '%s\n' "ERROR: $*" >&2
    exit 1
}

[ -d "$KLIPPER_DIR/.git" ] || fail "Klipper git tree not found: $KLIPPER_DIR"
[ -f "$PAYLOAD/core-2817b348.patch" ] || fail "Backport payload is incomplete"
[ -f "$CAPTURE_MODULE" ] || fail "autopa_capture.py is missing"

commit=$(git -C "$KLIPPER_DIR" rev-parse HEAD)
[ "$commit" = "$EXPECTED_COMMIT" ] || fail \
    "Expected Klipper $EXPECTED_COMMIT, found $commit"

for path in klippy/extras/load_cell.py src/Kconfig src/Makefile; do
    git -C "$KLIPPER_DIR" diff --quiet -- "$path" ||
        fail "Refusing to modify locally changed file: $path"
done

check_target_absent() {
    [ ! -e "$KLIPPER_DIR/$1" ] ||
        fail "Target already exists; inspect or restore first: $1"
}

check_target_absent klippy/extras/ads131m0x.py
check_target_absent klippy/extras/static_pwm_clock.py
check_target_absent klippy/extras/autopa_capture.py
check_target_absent src/sensor_ads131m0x.c

patch --dry-run --silent --no-backup-if-mismatch -d "$KLIPPER_DIR" -p1 \
    < "$PAYLOAD/core-2817b348.patch" ||
    fail "Core patch does not apply cleanly"

if [ "$MODE" = "--check" ]; then
    printf '%s\n' "Backport preflight passed for $commit"
    exit 0
fi
[ "$MODE" = "--install" ] || fail "Usage: $0 [--check|--install]"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="$KLIPPER_DIR/.autopa-backup/$stamp"
mkdir -p "$backup/klippy/extras" "$backup/src"
cp -p "$KLIPPER_DIR/klippy/extras/load_cell.py" "$backup/klippy/extras/"
cp -p "$KLIPPER_DIR/src/Kconfig" "$backup/src/"
cp -p "$KLIPPER_DIR/src/Makefile" "$backup/src/"

cp -p "$PAYLOAD/klippy/extras/ads131m0x.py" \
    "$KLIPPER_DIR/klippy/extras/ads131m0x.py"
cp -p "$PAYLOAD/klippy/extras/static_pwm_clock.py" \
    "$KLIPPER_DIR/klippy/extras/static_pwm_clock.py"
cp -p "$PAYLOAD/src/sensor_ads131m0x.c" \
    "$KLIPPER_DIR/src/sensor_ads131m0x.c"
cp -p "$CAPTURE_MODULE" "$KLIPPER_DIR/klippy/extras/autopa_capture.py"
patch --silent --no-backup-if-mismatch -d "$KLIPPER_DIR" -p1 \
    < "$PAYLOAD/core-2817b348.patch"

printf '%s\n' "Installed AutoPA Klipper backport."
printf '%s\n' "Backup: $backup"
printf '%s\n' "Klipper was not restarted and no MCU was flashed."
