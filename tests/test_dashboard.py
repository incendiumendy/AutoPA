import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from autopa.dashboard import build_dashboard_status, make_handler


class DashboardStatusTests(unittest.TestCase):
    def printer(self):
        return {
            "webhooks": {
                "state": "ready",
                "state_message": "Printer is ready",
            },
            "print_stats": {"state": "standby"},
            "extruder": {
                "temperature": 210.2,
                "target": 210.0,
                "pressure_advance": 0.03,
                "smooth_time": 0.02,
            },
            "configfile": {
                "settings": {
                    "extruder": {
                        "nozzle_diameter": 0.6,
                        "filament_diameter": 1.75,
                        "max_extrude_cross_section": 1.44,
                    },
                },
            },
            "firmware_retraction": {
                "retract_length": 0.8,
                "retract_speed": 35.0,
            },
        }

    def test_fresh_capture_is_ok(self):
        now = 20_000_000_000
        live = {
            "state": "capturing",
            "dataset": "test",
            "updated_host_monotonic_ns": now - 100_000_000,
            "force": {"filtered": 1234},
            "acceleration": {
                "x_mm_s2": 3,
                "y_mm_s2": 4,
                "z_mm_s2": 0,
                "motion_x_mm_s2": 1200,
                "motion_y_mm_s2": -800,
                "motion_z_mm_s2": 350,
                "rms_x_mm_s2": 420,
                "rms_y_mm_s2": 310,
                "rms_z_mm_s2": 90,
                "errors": 0,
                "overflows": 0,
            },
            "sample_rates_hz": {
                "force": 2597,
                "acceleration": 386,
            },
        }
        result = build_dashboard_status(
            self.printer(), live, now_monotonic_ns=now,
            control_status={
                "printerAction": "none",
                "pressure": {
                    "baseline": 1000,
                    "delta": 234,
                    "normalized": 0.75,
                },
            })
        self.assertEqual("ok", result["quality"]["state"])
        self.assertEqual(5.0, result["sensors"]["lis2dw"]["magnitude"])
        self.assertEqual(
            5.0, result["sensors"]["accelerometer"]["magnitude"])
        self.assertEqual(
            1200.0, result["sensors"]["accelerometer"]["motionX"])
        self.assertEqual(
            -800.0, result["sensors"]["accelerometer"]["motionY"])
        self.assertEqual(
            350.0, result["sensors"]["accelerometer"]["motionZ"])
        self.assertEqual(
            420.0, result["sensors"]["accelerometer"]["rmsX"])
        self.assertEqual(0.6, result["printer"]["nozzleDiameter"])
        self.assertEqual(1.75, result["printer"]["filamentDiameter"])
        self.assertTrue(
            result["printer"]["firmwareRetractionAvailable"])
        self.assertEqual(0.8, result["printer"]["retractLength"])
        self.assertEqual(1000.0, result["sensors"]["alps"]["baseline"])
        self.assertEqual(234.0, result["sensors"]["alps"]["delta"])
        self.assertEqual(0.75, result["sensors"]["alps"]["normalized"])
        self.assertEqual("none", result["safety"]["printerAction"])

    def test_optional_accelerometer_is_healthy_when_disabled(self):
        now = 20_000_000_000
        live = {
            "state": "capturing",
            "dataset": "force-only",
            "accelerometer_config": {
                "enabled": False,
                "type": "none",
                "name": None,
            },
            "updated_host_monotonic_ns": now - 100_000_000,
            "force": {"filtered": 1234},
            "sample_rates_hz": {"force": 2597, "acceleration": 0},
        }
        result = build_dashboard_status(
            self.printer(), live, now_monotonic_ns=now)
        self.assertEqual("ok", result["quality"]["state"])
        self.assertFalse(result["sensors"]["accelerometer"]["enabled"])
        self.assertIn("optional", result["quality"]["message"])

    def test_idle_sensor_state_is_waiting_not_error(self):
        result = build_dashboard_status(
            self.printer(), {}, now_monotonic_ns=1)
        self.assertEqual("waiting", result["quality"]["state"])
        self.assertEqual("waiting", result["sensors"]["alps"]["state"])
        self.assertTrue(result["printer"]["connected"])

    def test_stale_active_capture_warns_without_printer_action(self):
        now = 20_000_000_000
        result = build_dashboard_status(self.printer(), {
            "state": "capturing",
            "updated_host_monotonic_ns": now - 5_000_000_000,
        }, now_monotonic_ns=now)
        self.assertEqual("warning", result["quality"]["state"])
        self.assertEqual("none", result["safety"]["printerAction"])

    def test_moonraker_error_is_reported(self):
        result = build_dashboard_status(
            {}, {}, now_monotonic_ns=1, error="connection refused")
        self.assertEqual("error", result["quality"]["state"])
        self.assertFalse(result["printer"]["connected"])

    def test_http_status_surface_rejects_unrelated_posts(self):
        expected = build_dashboard_status(
            self.printer(), {}, now_monotonic_ns=1)

        class Data:
            def status(self):
                return expected

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text(
                "<!doctype html><title>AutoPA</title>", encoding="utf-8")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), make_handler(Data(), directory))
            thread = threading.Thread(
                target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:%d" % server.server_port
            try:
                with urllib.request.urlopen(
                        base + "/api/status") as response:
                    payload = json.load(response)
                self.assertEqual(
                    "none", payload["safety"]["printerAction"])
                with urllib.request.urlopen(base + "/") as response:
                    self.assertIn(b"AutoPA", response.read())
                with urllib.request.urlopen(
                        base + "/autopa/api/status") as response:
                    prefixed_payload = json.load(response)
                self.assertEqual(
                    "none",
                    prefixed_payload["safety"]["printerAction"])
                request = urllib.request.Request(
                    base + "/api/status", method="POST", data=b"{}")
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request)
                self.assertEqual(405, raised.exception.code)
                raised.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)

    def test_http_control_surface_routes_bounded_actions(self):
        class Data:
            def __init__(self):
                self.config = None
                self.disarmed = False

            def control_status(self):
                return {"mode": "dry_run", "armed": False}

            def update_control(self, payload):
                self.config = payload
                return {"mode": payload["mode"], "armed": False}

            def arm_control(self, payload):
                raise PermissionError(
                    "printer commands are server-side locked")

            def disarm_control(self):
                self.disarmed = True
                return {"mode": "dry_run", "armed": False}

        data = Data()
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text(
                "<!doctype html><title>AutoPA</title>", encoding="utf-8")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), make_handler(data, directory))
            thread = threading.Thread(
                target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:%d" % server.server_port
            try:
                with urllib.request.urlopen(
                        base + "/api/control") as response:
                    self.assertEqual(
                        "dry_run", json.load(response)["mode"])
                body = json.dumps({
                    "mode": "dry_run",
                    "adaptive_pa_enabled": True,
                }).encode("utf-8")
                request = urllib.request.Request(
                    base + "/api/control/config", method="POST",
                    data=body,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(
                        "dry_run", json.load(response)["mode"])
                self.assertTrue(data.config["adaptive_pa_enabled"])
                request = urllib.request.Request(
                    base + "/api/control/arm", method="POST",
                    data=json.dumps({
                        "phrase": "AUTOPA VALIDIEREN",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request)
                self.assertEqual(403, raised.exception.code)
                raised.exception.close()
                request = urllib.request.Request(
                    base + "/api/control/disarm",
                    method="POST", data=b"{}",
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request):
                    pass
                self.assertTrue(data.disarmed)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)

    def test_http_capture_surface_routes_passive_start_and_stop(self):
        class Data:
            def __init__(self):
                self.started = None
                self.stopped = False

            def capture_status(self):
                return {
                    "state": "idle",
                    "active": False,
                    "printerAction": "none",
                }

            def start_capture(self, payload):
                self.started = payload
                return {
                    "state": "capturing",
                    "active": True,
                    "printerAction": "none",
                }

            def stop_capture(self):
                self.stopped = True
                return {
                    "state": "stopping",
                    "active": True,
                    "printerAction": "none",
                }

        data = Data()
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text(
                "<!doctype html><title>AutoPA</title>", encoding="utf-8")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), make_handler(data, directory))
            thread = threading.Thread(
                target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:%d" % server.server_port
            try:
                with urllib.request.urlopen(
                        base + "/api/capture") as response:
                    self.assertEqual(
                        "none", json.load(response)["printerAction"])
                request = urllib.request.Request(
                    base + "/api/capture/start", method="POST",
                    data=b'{"name":"benchy"}',
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request) as response:
                    self.assertTrue(json.load(response)["active"])
                self.assertEqual("benchy", data.started["name"])
                request = urllib.request.Request(
                    base + "/api/capture/stop", method="POST", data=b"{}",
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request):
                    pass
                self.assertTrue(data.stopped)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)

    def test_http_filter_surface_saves_profiles_without_direct_gcode(self):
        class Data:
            def __init__(self):
                self.profiles = None

            def filter_status(self):
                return {
                    "state": "idle",
                    "allowCommands": False,
                    "availableFans": ["chamber_filter"],
                    "printerAction": "none",
                }

            def update_filter(self, payload):
                self.profiles = payload["profiles"]
                return {
                    "state": "idle",
                    "allowCommands": False,
                    "availableFans": ["chamber_filter"],
                    "configuredProfiles": len(self.profiles),
                    "printerAction": "none",
                }

        data = Data()
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text(
                "<!doctype html><title>AutoPA</title>", encoding="utf-8")
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), make_handler(data, directory))
            thread = threading.Thread(
                target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:%d" % server.server_port
            try:
                with urllib.request.urlopen(
                        base + "/api/filter") as response:
                    payload = json.load(response)
                self.assertEqual(["chamber_filter"],
                                 payload["availableFans"])
                body = json.dumps({"profiles": [{
                    "id": "abs",
                    "filter_enabled": True,
                }]}).encode("utf-8")
                request = urllib.request.Request(
                    base + "/api/filter/config", method="POST", data=body,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(
                        1, json.load(response)["configuredProfiles"])
                self.assertEqual("abs", data.profiles[0]["id"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)


if __name__ == "__main__":
    unittest.main()
