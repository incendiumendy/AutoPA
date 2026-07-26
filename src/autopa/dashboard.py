"""Read-only local dashboard server for Moonraker and AutoPA live data."""
import argparse
import json
import math
import mimetypes
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


MOONRAKER_QUERY = (
    "/printer/objects/query?webhooks&print_stats&extruder&configfile")


def _number(value):
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def build_dashboard_status(printer_status, live_status,
                           now_monotonic_ns=None, error=None):
    """Create the stable browser API without issuing printer commands."""
    now_monotonic_ns = now_monotonic_ns or time.monotonic_ns()
    printer_status = printer_status or {}
    live_status = live_status or {}
    webhooks = printer_status.get("webhooks", {})
    print_stats = printer_status.get("print_stats", {})
    extruder = printer_status.get("extruder", {})
    config_extruder = (
        printer_status.get("configfile", {})
        .get("settings", {})
        .get("extruder", {}))
    connected = webhooks.get("state") == "ready" and not error

    updated_ns = live_status.get("updated_host_monotonic_ns")
    age_seconds = (
        max(0., (now_monotonic_ns - updated_ns) / 1e9)
        if isinstance(updated_ns, int) else None)
    capturing = live_status.get("state") == "capturing"
    fresh = capturing and age_seconds is not None and age_seconds <= 2.
    live_error = live_status.get("state") == "error"

    force = live_status.get("force") or {}
    acceleration = live_status.get("acceleration") or {}
    accelerometer_config = live_status.get("accelerometer_config") or {}
    accelerometer_enabled = accelerometer_config.get("enabled", True)
    accelerometer_type = accelerometer_config.get("type", "lis2dw")
    accelerometer_name = accelerometer_config.get("name")
    sample_rates = live_status.get("sample_rates_hz") or {}
    accel_components = [
        _number(acceleration.get("x_mm_s2")),
        _number(acceleration.get("y_mm_s2")),
        _number(acceleration.get("z_mm_s2")),
    ]
    magnitude = (
        math.sqrt(sum(value * value for value in accel_components))
        if all(value is not None for value in accel_components) else None)
    accel_fault = (
        (acceleration.get("errors") or 0) > 0
        or (acceleration.get("overflows") or 0) > 0)

    if error:
        quality_state = "error"
        quality_message = "Moonraker ist nicht erreichbar: %s" % error
    elif live_error:
        quality_state = "warning"
        quality_message = (
            "Die letzte Aufnahme meldet einen Fehler; der Druck läuft weiter.")
    elif (fresh and force
          and (not accelerometer_enabled
               or acceleration and not accel_fault)):
        quality_state = "ok"
        quality_message = (
            "Kraftdaten sind frisch; Beschleunigung ist optional deaktiviert."
            if not accelerometer_enabled else
            "Alle Datenströme sind frisch und die Messkette ist aktiv.")
    elif capturing and not fresh:
        quality_state = "warning"
        quality_message = (
            "Die Aufnahme läuft, aber die Live-Daten sind nicht aktuell.")
    else:
        quality_state = "waiting"
        quality_message = (
            "Drucker bereit; Live-Sensoren starten mit der nächsten Aufnahme.")

    sensor_idle_state = "warning" if live_error else "waiting"
    alps_state = "ok" if fresh and force else sensor_idle_state
    accelerometer_state = (
        "ok" if not accelerometer_enabled
        else "warning" if accel_fault
        else "ok" if fresh and acceleration
        else sensor_idle_state)
    capture_state = (
        "ok" if fresh
        else "warning" if capturing or live_error
        else "waiting")

    return {
        "timestamp": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "demo": False,
        "printer": {
            "connected": connected,
            "state": (
                "Klipper bereit" if connected
                else webhooks.get("state_message")
                or "Moonraker nicht erreichbar"),
            "printState": print_stats.get("state", "unbekannt"),
            "temperature": _number(extruder.get("temperature")),
            "target": _number(extruder.get("target")),
            "pressureAdvance": _number(extruder.get("pressure_advance")),
            "smoothTime": _number(extruder.get("smooth_time")),
            "nozzleDiameter": _number(
                config_extruder.get("nozzle_diameter")),
            "filamentDiameter": _number(
                config_extruder.get("filament_diameter")),
            "maxExtrudeCrossSection": _number(
                config_extruder.get("max_extrude_cross_section")),
        },
        "capture": {
            "state": capture_state,
            "dataset": live_status.get("dataset"),
            "ageSeconds": age_seconds,
        },
        "sensors": {
            "alps": {
                "state": alps_state,
                "value": _number(force.get("filtered")),
                "sampleRate": _number(sample_rates.get("force")),
            },
            "accelerometer": {
                "enabled": accelerometer_enabled,
                "type": accelerometer_type,
                "name": accelerometer_name,
                "state": accelerometer_state,
                "magnitude": magnitude,
                "sampleRate": _number(sample_rates.get("acceleration")),
            },
            "lis2dw": {
                "state": accelerometer_state,
                "magnitude": magnitude,
                "sampleRate": _number(sample_rates.get("acceleration")),
            },
        },
        "quality": {
            "state": quality_state,
            "message": quality_message,
        },
        "safety": {
            "printerAction": "none",
        },
    }


class DashboardData:
    def __init__(self, moonraker_url, live_status_path):
        self.moonraker_url = moonraker_url.rstrip("/")
        self.live_status_path = Path(live_status_path).expanduser()

    def _printer_status(self):
        request = urllib.request.Request(
            self.moonraker_url + MOONRAKER_QUERY,
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.load(response)
        return payload["result"]["status"]

    def _live_status(self):
        try:
            with self.live_status_path.open(
                    "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def status(self):
        try:
            printer_status = self._printer_status()
            error = None
        except (KeyError, OSError, ValueError,
                urllib.error.URLError) as exc:
            printer_status = {}
            error = str(exc)
        return build_dashboard_status(
            printer_status, self._live_status(), error=error)


def make_handler(data, static_dir):
    static_root = Path(static_dir).resolve()

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "AutoPADashboard/0.1"

        def _send_json(self, payload, status=200):
            body = json.dumps(
                payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            request_path = parsed.path
            if request_path.startswith("/autopa/"):
                request_path = "/" + request_path[len("/autopa/"):]
            if request_path == "/api/status":
                self._send_json(data.status())
                return
            if request_path == "/api/health":
                self._send_json({
                    "status": "ok",
                    "printer_control": "none",
                })
                return

            relative = request_path.lstrip("/") or "index.html"
            candidate = (static_root / relative).resolve()
            if static_root not in candidate.parents and candidate != static_root:
                self.send_error(403)
                return
            if not candidate.is_file():
                candidate = static_root / "index.html"
            if not candidate.is_file():
                self.send_error(
                    503, "Dashboard assets are not built")
                return
            body = candidate.read_bytes()
            content_type = (
                mimetypes.guess_type(candidate.name)[0]
                or "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header(
                "Cache-Control",
                "no-cache" if candidate.name == "index.html"
                else "public, max-age=31536000, immutable")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self._send_json({
                "error": "read-only dashboard",
                "printer_action": "none",
            }, status=405)

        def log_message(self, message, *args):
            print("%s - %s" % (self.address_string(), message % args))

    return DashboardHandler


def main():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Serve the read-only AutoPA live dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7126)
    parser.add_argument(
        "--moonraker-url", default="http://127.0.0.1:7125")
    parser.add_argument(
        "--live-status",
        default=os.path.expanduser("~/printer_data/autopa/live.json"))
    parser.add_argument(
        "--static-dir",
        default=str(project_root / "dashboard" / "dist" / "client"))
    args = parser.parse_args()
    data = DashboardData(args.moonraker_url, args.live_status)
    server = ThreadingHTTPServer(
        (args.host, args.port), make_handler(data, args.static_dir))
    print("AutoPA dashboard listening on http://%s:%d" % (
        args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
