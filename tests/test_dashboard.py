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
                "errors": 0,
                "overflows": 0,
            },
            "sample_rates_hz": {
                "force": 2597,
                "acceleration": 386,
            },
        }
        result = build_dashboard_status(
            self.printer(), live, now_monotonic_ns=now)
        self.assertEqual("ok", result["quality"]["state"])
        self.assertEqual(5.0, result["sensors"]["lis2dw"]["magnitude"])
        self.assertEqual(
            5.0, result["sensors"]["accelerometer"]["magnitude"])
        self.assertEqual(0.6, result["printer"]["nozzleDiameter"])
        self.assertEqual(1.75, result["printer"]["filamentDiameter"])
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

    def test_http_surface_is_read_only(self):
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


if __name__ == "__main__":
    unittest.main()
