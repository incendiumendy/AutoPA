"""Local AutoPA dashboard with bounded, explicitly armed runtime control."""
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

import threading

from .adaptive import AdaptiveController
from .analyze import analyze_dataset
from .capture_manager import CaptureManager
from .chamber_filter import ChamberFilterController
from .quality import assess_dataset
from .retract_analyze import analyze_retract_dataset
from .retract_runner import RetractSweepRunner
from .pa_runner import PaSweepRunner
from .sync_recorder import ACCELEROMETER_ENDPOINTS


MOONRAKER_QUERY = (
    "/printer/objects/query?"
    "webhooks&print_stats&extruder&configfile&firmware_retraction")


def _number(value):
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def build_dashboard_status(printer_status, live_status,
                           now_monotonic_ns=None, error=None,
                           control_status=None, capture_manager_status=None,
                           chamber_filter_status=None):
    """Create the stable browser API and report opt-in controller state."""
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
    firmware_retraction = printer_status.get("firmware_retraction") or {}
    connected = webhooks.get("state") == "ready" and not error

    updated_ns = live_status.get("updated_host_monotonic_ns")
    age_seconds = (
        max(0., (now_monotonic_ns - updated_ns) / 1e9)
        if isinstance(updated_ns, int) else None)
    capturing = live_status.get("state") == "capturing"
    fresh = capturing and age_seconds is not None and age_seconds <= 2.
    live_error = live_status.get("state") == "error"

    force = live_status.get("force") or {}
    control_status = control_status or {}
    capture_manager_status = capture_manager_status or {
        "state": "disabled",
        "active": False,
        "canStart": False,
        "canStop": False,
        "printerAction": "none",
    }
    chamber_filter_status = chamber_filter_status or {
        "state": "disabled",
        "allowCommands": False,
        "availableFans": [],
        "printerAction": "none",
    }
    controlled_pressure = control_status.get("pressure") or {}
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
            "firmwareRetractionAvailable": (
                bool(firmware_retraction)
                or bool(control_status.get(
                    "firmwareRetractionAvailable"))),
            "retractLength": _number(
                firmware_retraction.get("retract_length")),
            "retractSpeed": _number(
                firmware_retraction.get("retract_speed")),
        },
        "capture": {
            "state": capture_state,
            "dataset": (
                capture_manager_status.get("dataset")
                or live_status.get("dataset")),
            "ageSeconds": age_seconds,
            "manager": capture_manager_status,
        },
        "sensors": {
            "alps": {
                "state": alps_state,
                "value": _number(force.get("filtered")),
                "baseline": _number(controlled_pressure.get("baseline")),
                "delta": _number(controlled_pressure.get("delta")),
                "normalized": _number(
                    controlled_pressure.get("normalized")),
                "sampleRate": _number(sample_rates.get("force")),
            },
            "accelerometer": {
                "enabled": accelerometer_enabled,
                "type": accelerometer_type,
                "name": accelerometer_name,
                "state": accelerometer_state,
                "magnitude": magnitude,
                "motionX": _number(
                    acceleration.get("motion_x_mm_s2")),
                "motionY": _number(
                    acceleration.get("motion_y_mm_s2")),
                "motionZ": _number(
                    acceleration.get("motion_z_mm_s2")),
                "rmsX": _number(acceleration.get("rms_x_mm_s2")),
                "rmsY": _number(acceleration.get("rms_y_mm_s2")),
                "rmsZ": _number(acceleration.get("rms_z_mm_s2")),
                "sampleRate": _number(sample_rates.get("acceleration")),
            },
            "lis2dw": {
                "state": accelerometer_state,
                "magnitude": magnitude,
                "motionX": _number(
                    acceleration.get("motion_x_mm_s2")),
                "motionY": _number(
                    acceleration.get("motion_y_mm_s2")),
                "motionZ": _number(
                    acceleration.get("motion_z_mm_s2")),
                "sampleRate": _number(sample_rates.get("acceleration")),
            },
        },
        "quality": {
            "state": quality_state,
            "message": quality_message,
        },
        "safety": {
            "printerAction": (
                chamber_filter_status.get("printerAction")
                if chamber_filter_status.get("printerAction") != "none"
                else control_status.get("printerAction", "none")),
        },
        "control": control_status,
        "chamberFilter": chamber_filter_status,
    }


class DashboardData:
    def __init__(self, moonraker_url, live_status_path, controller=None,
                 capture_manager=None, chamber_filter=None,
                 sweep_runner=None, pa_sweep_runner=None,
                 quality_fn=None, retract_analyzer=None, pa_analyzer=None,
                 sleep_fn=None):
        self.moonraker_url = moonraker_url.rstrip("/")
        self.live_status_path = Path(live_status_path).expanduser()
        self.controller = controller
        self.capture_manager = capture_manager
        self.chamber_filter = chamber_filter
        self.sweep_runner = sweep_runner
        self.pa_sweep_runner = pa_sweep_runner
        self.quality_fn = quality_fn or assess_dataset
        self.retract_analyzer = retract_analyzer or analyze_retract_dataset
        self.pa_analyzer = pa_analyzer or analyze_dataset
        self.sleep_fn = sleep_fn or time.sleep

    def sweep_status(self):
        return (
            self.sweep_runner.status() if self.sweep_runner else {
                "allowPrinterCommands": False,
                "confirmationPhraseRequired": True,
                "lastRun": None,
                "lastError": "sweep_runner_disabled",
                "printerAction": "none",
            })

    def run_sweep(self, payload):
        if not self.sweep_runner:
            raise RuntimeError("sweep runner disabled")
        started_capture = self._maybe_start_sweep_capture(
            payload, "retract-sweep")
        try:
            status = self.sweep_runner.run(payload)
        except Exception:
            self._stop_started_capture(started_capture, "sweep_rejected")
            raise
        self._schedule_post_sweep("retract", started_capture)
        return status

    def pa_sweep_status(self):
        return (
            self.pa_sweep_runner.status() if self.pa_sweep_runner else {
                "allowPrinterCommands": False,
                "confirmationPhraseRequired": True,
                "lastRun": None,
                "lastError": "pa_sweep_runner_disabled",
                "printerAction": "none",
            })

    def run_pa_sweep(self, payload):
        if not self.pa_sweep_runner:
            raise RuntimeError("pa sweep runner disabled")
        started_capture = self._maybe_start_sweep_capture(
            payload, "pa-sweep")
        try:
            status = self.pa_sweep_runner.run(payload)
        except Exception:
            self._stop_started_capture(started_capture, "sweep_rejected")
            raise
        self._schedule_post_sweep("pa", started_capture)
        return status

    def _maybe_start_sweep_capture(self, payload, name):
        """Auto-start a capture so the sweep can be analyzed afterwards."""
        if not isinstance(payload, dict):
            return False
        if not payload.get("auto_apply", True):
            return False
        manager = self.capture_manager
        if manager is None:
            return False
        try:
            if not manager.status().get("canStart"):
                return False
            manager.start("standby", name)
            return True
        except Exception:
            # A failed capture never blocks the confirmed sweep itself.
            return False

    def _stop_started_capture(self, started_capture, reason):
        if not started_capture or self.capture_manager is None:
            return
        try:
            self.capture_manager.stop(reason)
        except Exception:
            pass

    def _schedule_post_sweep(self, kind, started_capture):
        runner = (
            self.sweep_runner if kind == "retract" else self.pa_sweep_runner)
        last_run = runner.last_run or {}
        if not last_run.get("autoApply"):
            if started_capture:
                self._stop_started_capture(True, "auto_apply_disabled")
            return
        duration = last_run.get("estimatedDurationS") or 0.0
        try:
            wait = min(max(float(duration), 0.0) + 20.0, 900.0)
        except (TypeError, ValueError):
            wait = 900.0
        thread = threading.Thread(
            target=self._post_sweep_pipeline,
            args=(kind, wait, started_capture),
            name="autopa-post-sweep-%s" % kind,
            daemon=True)
        thread.start()

    def _post_sweep_pipeline(self, kind, wait, started_capture):
        runner = (
            self.sweep_runner if kind == "retract" else self.pa_sweep_runner)
        analyzer = (
            self.retract_analyzer if kind == "retract" else self.pa_analyzer)
        key = (
            "retract_length_mm" if kind == "retract" else "pressure_advance")
        source = None
        try:
            self.sleep_fn(wait)
            dataset_dir = self._finish_sweep_capture(started_capture)
            if not dataset_dir:
                runner.record_apply_skip("no_capture_dataset")
                return
            source = os.path.basename(dataset_dir)
            try:
                self.quality_fn(dataset_dir)
            except Exception:
                # A missing quality gate fails the analysis closed.
                pass
            result = analyzer(dataset_dir) or {}
            recommendation = result.get("recommendation")
            if not recommendation or recommendation.get(key) is None:
                runner.record_apply_skip("no_recommendation", source=source)
                return
            runner.apply_recommendation(recommendation[key], source=source)
        except Exception:
            runner.record_apply_skip("analysis_failed", source=source)

    def _finish_sweep_capture(self, started_capture):
        manager = self.capture_manager
        if manager is None:
            return None
        if started_capture:
            self._stop_started_capture(True, "sweep_finished")
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                if not manager.status().get("active"):
                    break
                self.sleep_fn(1.0)
        status = manager.status()
        if status.get("active"):
            return None
        dataset = status.get("dataset")
        if not dataset:
            return None
        candidate = os.path.join(manager.output_root, dataset)
        return candidate if os.path.isdir(candidate) else None

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
        if self.controller:
            retraction = printer_status.get("firmware_retraction") or {}
            retract_length = _number(retraction.get("retract_length"))
            self.controller.firmware_retraction_available = bool(retraction)
            if retract_length is not None:
                self.controller.current_retract = retract_length
            control_status = self.controller.status()
        else:
            control_status = None
        return build_dashboard_status(
            printer_status, self._live_status(), error=error,
            control_status=control_status,
            capture_manager_status=self.capture_status(),
            chamber_filter_status=self.filter_status())

    def filter_status(self):
        return (
            self.chamber_filter.status() if self.chamber_filter else {
                "state": "disabled",
                "allowCommands": False,
                "availableFans": [],
                "filename": None,
                "matchedProfile": None,
                "activeFan": None,
                "activeSpeedPercent": None,
                "postRunSecondsRemaining": 0.0,
                "configuredProfiles": 0,
                "lastCommand": None,
                "lastError": None,
                "commandCount": 0,
                "printerAction": "none",
            })

    def update_filter(self, payload):
        if not self.chamber_filter:
            raise RuntimeError("Chamber-Filter-Controller ist deaktiviert")
        return self.chamber_filter.update_profiles(
            payload.get("profiles"))

    def capture_status(self):
        return (
            self.capture_manager.status() if self.capture_manager else {
                "state": "disabled",
                "active": False,
                "canStart": False,
                "canStop": False,
                "dataset": None,
                "mode": "disabled",
                "attachedToPrint": False,
                "stopReason": None,
                "error": None,
                "monitorError": None,
                "stats": None,
                "printerAction": "none",
            })

    def start_capture(self, payload):
        if not self.capture_manager:
            raise RuntimeError("Recorder-Manager ist deaktiviert")
        printer_status = self._printer_status()
        print_stats = printer_status.get("print_stats") or {}
        print_state = print_stats.get("state")
        requested_name = str(payload.get("name", "")).strip()
        filename = Path(str(print_stats.get("filename", ""))).stem
        default_name = filename if print_state == "printing" else "live-preview"
        return self.capture_manager.start(
            print_state, requested_name or default_name or "print")

    def stop_capture(self):
        if not self.capture_manager:
            raise RuntimeError("Recorder-Manager ist deaktiviert")
        return self.capture_manager.stop()

    def control_status(self):
        return (
            self.controller.status() if self.controller else {
                "mode": "off",
                "allowPrinterCommands": False,
                "armed": False,
                "printerAction": "none",
                "reason": "controller_disabled",
            })

    def update_control(self, payload):
        if not self.controller:
            raise RuntimeError("controller disabled")
        return self.controller.update_config(payload)

    def arm_control(self, payload):
        if not self.controller:
            raise RuntimeError("controller disabled")
        return self.controller.arm(str(payload.get("phrase", "")))

    def disarm_control(self):
        if not self.controller:
            raise RuntimeError("controller disabled")
        return self.controller.disarm()


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
                    "printer_control": (
                        "opt_in_bounded"
                        if data.controller else "none"),
                })
                return
            if request_path == "/api/control":
                self._send_json(data.control_status())
                return
            if request_path == "/api/capture":
                self._send_json(data.capture_status())
                return
            if request_path == "/api/filter":
                self._send_json(data.filter_status())
                return
            if request_path == "/api/sweep":
                self._send_json(data.sweep_status())
            if request_path == "/api/pa-sweep":
                self._send_json(data.pa_sweep_status())
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
            parsed = urlparse(self.path)
            request_path = parsed.path
            if request_path.startswith("/autopa/"):
                request_path = "/" + request_path[len("/autopa/"):]
            if request_path not in {
                     "/api/control/config",
                     "/api/control/arm",
                     "/api/control/disarm",
                     "/api/capture/start",
                     "/api/capture/stop",
                     "/api/filter/config",
                     "/api/sweep/run", "/api/pa-sweep/run"}:
                self._send_json({
                    "error": "unsupported endpoint",
                    "printer_action": "none",
                }, status=405)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 16384:
                    raise ValueError("request too large")
                payload = (
                    json.loads(self.rfile.read(length).decode("utf-8"))
                    if length else {})
                if request_path == "/api/control/config":
                    result = data.update_control(payload)
                elif request_path == "/api/control/arm":
                    result = data.arm_control(payload)
                elif request_path == "/api/control/disarm":
                    result = data.disarm_control()
                elif request_path == "/api/capture/start":
                    result = data.start_capture(payload)
                elif request_path == "/api/capture/stop":
                    result = data.stop_capture()
                elif request_path == "/api/sweep/run":
                    result = data.run_sweep(payload)
                elif request_path == "/api/pa-sweep/run":
                    result = data.run_pa_sweep(payload)
                else:
                    result = data.update_filter(payload)
                self._send_json(result)
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, status=403)
            except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
                self._send_json({"error": str(exc)}, status=400)

        def log_message(self, message, *args):
            print("%s - %s" % (self.address_string(), message % args))

    return DashboardHandler


def main():
    project_root = Path(__file__).resolve().parents[2]
    configured_control_state = os.environ.get("AUTOPA_CONTROL_STATE")
    managed_state_root = (
        os.path.dirname(os.path.abspath(os.path.expanduser(
            configured_control_state)))
        if configured_control_state else None)
    default_live_status = (
        os.path.join(managed_state_root, "live.json")
        if managed_state_root
        else os.path.expanduser("~/printer_data/autopa/live.json"))
    default_output_root = (
        os.path.join(managed_state_root, "captures")
        if managed_state_root
        else os.path.expanduser("~/printer_data/autopa"))
    default_filter_state = (
        os.path.join(managed_state_root, "chamber-filter.json")
        if managed_state_root
        else os.path.expanduser(
            "~/.local/state/autopa/chamber-filter.json"))
    parser = argparse.ArgumentParser(
        description="Serve the read-only AutoPA live dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7126)
    parser.add_argument(
        "--moonraker-url", default="http://127.0.0.1:7125")
    parser.add_argument(
        "--live-status",
        default=os.path.expanduser(os.environ.get(
            "AUTOPA_LIVE_STATUS", default_live_status)))
    parser.add_argument(
        "--static-dir",
        default=str(project_root / "dashboard" / "dist" / "client"))
    parser.add_argument(
        "--control-state",
        default=os.path.expanduser(
            os.environ.get(
                "AUTOPA_CONTROL_STATE",
                "~/.local/state/autopa/control.json")))
    parser.add_argument(
        "--allow-printer-commands", action="store_true",
        default=os.environ.get(
            "AUTOPA_ALLOW_PRINTER_COMMANDS", "0") == "1",
        help=("Unlock transient, bounded PA/retraction commands. "
              "The dashboard still requires the confirmation phrase."))
    parser.add_argument(
        "--alps-device",
        default=os.environ.get("AUTOPA_ALPS_DEVICE"),
        help=("Factory FLY-ALPS serial device. If omitted, one unique "
              "PressureLeveling USB device is discovered."))
    parser.add_argument(
        "--klippy-socket",
        default=os.path.expanduser(os.environ.get(
            "AUTOPA_KLIPPY_SOCKET",
            "~/printer_data/comms/klippy.sock")))
    parser.add_argument(
        "--output-root",
        default=os.path.expanduser(os.environ.get(
            "AUTOPA_OUTPUT_ROOT", default_output_root)))
    parser.add_argument(
        "--accelerometer", default=os.environ.get(
            "AUTOPA_ACCELEROMETER", "toolboard_t0"))
    parser.add_argument(
        "--accelerometer-type",
        choices=(*ACCELEROMETER_ENDPOINTS, "none"),
        default=os.environ.get("AUTOPA_ACCELEROMETER_TYPE", "lis2dw"))
    parser.add_argument(
        "--capture-max-duration", type=float,
        default=float(os.environ.get(
            "AUTOPA_CAPTURE_MAX_DURATION", 12 * 60 * 60)))
    parser.add_argument(
        "--filter-state",
        default=os.path.expanduser(os.environ.get(
            "AUTOPA_FILTER_STATE", default_filter_state)))
    parser.add_argument(
        "--allow-filter-commands", action="store_true",
        default=os.environ.get(
            "AUTOPA_ALLOW_FILTER_COMMANDS", "0") == "1",
        help=("Unlock only validated SET_FAN_SPEED commands for configured "
              "fan_generic chamber filters."))
    args = parser.parse_args()
    controller = AdaptiveController(
        args.live_status, args.control_state,
        moonraker_url=args.moonraker_url,
        allow_printer_commands=args.allow_printer_commands)
    controller.start()

    def current_print_state():
        request = urllib.request.Request(
            args.moonraker_url
            + "/printer/objects/query?print_stats",
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.load(response)
        return (
            payload.get("result", {}).get("status", {})
            .get("print_stats", {}).get("state"))

    capture_manager = CaptureManager(
        args.alps_device, args.klippy_socket, args.output_root,
        args.live_status, args.accelerometer, args.accelerometer_type,
        print_state_provider=current_print_state,
        max_duration=args.capture_max_duration)
    chamber_filter = ChamberFilterController(
        args.filter_state, moonraker_url=args.moonraker_url,
        allow_commands=args.allow_filter_commands)
    chamber_filter.start()
    sweep_runner = RetractSweepRunner(
        moonraker_url=args.moonraker_url,
        allow_printer_commands=args.allow_printer_commands)
    pa_sweep_runner = PaSweepRunner(
        moonraker_url=args.moonraker_url,
        allow_printer_commands=args.allow_printer_commands)
    data = DashboardData(
        args.moonraker_url, args.live_status, controller=controller,
        capture_manager=capture_manager, chamber_filter=chamber_filter,
        sweep_runner=sweep_runner,
        pa_sweep_runner=pa_sweep_runner)
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
        chamber_filter.stop()
        capture_manager.shutdown()
        controller.stop()


if __name__ == "__main__":
    main()
