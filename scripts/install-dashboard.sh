#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SERVICE_TEMPLATE="$PROJECT_DIR/config/autopa-dashboard.service.example"
STATIC_INDEX="$PROJECT_DIR/dashboard/dist/client/index.html"
SERVICE_NAME=autopa-dashboard.service
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
AUTOPA_USER=${AUTOPA_DASHBOARD_USER:-$(id -un)}
TEMP_UNIT=$(mktemp)

cleanup() {
    rm -f "$TEMP_UNIT"
}
trap cleanup EXIT HUP INT TERM

[ -f "$SERVICE_TEMPLATE" ] || {
    printf '%s\n' "Missing service template: $SERVICE_TEMPLATE" >&2
    exit 1
}
[ -f "$STATIC_INDEX" ] || {
    printf '%s\n' "Dashboard assets are not built: $STATIC_INDEX" >&2
    exit 1
}

sed \
    -e "s|AUTOPA_USER|$AUTOPA_USER|g" \
    -e "s|AUTOPA_PROJECT_DIR|$PROJECT_DIR|g" \
    "$SERVICE_TEMPLATE" > "$TEMP_UNIT"

sudo install -m 0644 "$TEMP_UNIT" "$SERVICE_PATH"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

printf '%s\n' "AutoPA dashboard installed: http://$(hostname -I | awk '{print $1}'):7126/"
printf '%s\n' "The service is read-only and never sends printer G-code."
