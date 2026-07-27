import pathlib
import threading
import time
import unittest

from autopa.capture_manager import CaptureManager


class FakeRecorder:
    def __init__(self, alps_device, klippy_socket, output_dir,
                 accelerometer, live_status_path, accelerometer_type):
        self.output_dir = output_dir
        self.stop_event = threading.Event()

    def run(self, duration):
        self.stop_event.wait(2.0)
        return {
            "stats": {
                "force_samples": 100,
                "acceleration_samples": 20,
            },
        }


class CaptureManagerTests(unittest.TestCase):
    def manager(self, directory, provider=lambda: "printing"):
        return CaptureManager(
            "/dev/fake-alps",
            "/tmp/klippy.sock",
            str(pathlib.Path(directory, "captures")),
            str(pathlib.Path(directory, "live.json")),
            print_state_provider=provider,
            monitor_interval=0.01,
            recorder_factory=FakeRecorder)

    def wait_for(self, manager, state, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if manager.status()["state"] == state:
                return manager.status()
            time.sleep(0.01)
        self.fail(
            "manager did not reach %s: %r" % (state, manager.status()))

    def test_capture_can_attach_mid_print_and_stop_cleanly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory)
            status = manager.start("printing", "mid-print")
            self.assertTrue(status["active"])
            self.assertTrue(status["attachedToPrint"])
            self.assertEqual("none", status["printerAction"])
            manager.stop()
            status = self.wait_for(manager, "complete")
            self.assertEqual("user", status["stopReason"])
            self.assertEqual(100, status["stats"]["force_samples"])
            self.assertFalse(status["active"])

    def test_capture_rejects_start_outside_print(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory)
            with self.assertRaisesRegex(RuntimeError, "printing"):
                manager.start("standby")

    def test_print_completion_stops_attached_capture(self):
        import tempfile
        state = {"value": "printing"}
        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(
                directory, provider=lambda: state["value"])
            manager.start("printing", "whole-print")
            state["value"] = "complete"
            status = self.wait_for(manager, "complete")
            self.assertEqual("print_finished", status["stopReason"])
            self.assertIsNone(status["error"])

    def test_monitor_failure_never_stops_capture(self):
        import tempfile

        def unavailable():
            raise OSError("Moonraker unavailable")

        with tempfile.TemporaryDirectory() as directory:
            manager = self.manager(directory, provider=unavailable)
            manager.start("printing", "fail-open")
            time.sleep(0.05)
            status = manager.status()
            self.assertTrue(status["active"])
            self.assertIn("Moonraker unavailable", status["monitorError"])
            manager.stop()
            self.wait_for(manager, "complete")


if __name__ == "__main__":
    unittest.main()
