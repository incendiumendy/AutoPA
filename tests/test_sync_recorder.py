import json
import pathlib
import queue
import socket
import sys
import tempfile
import time
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))
from autopa.sync_recorder import (
    ACCELEROMETER_ENDPOINTS, ETX, KlippyConnection, SynchronizedRecorder)


class KlippyConnectionTest(unittest.TestCase):
    def setUp(self):
        self.client, self.server = socket.socketpair()
        self.connection = KlippyConnection("unused")
        self.connection.sock = self.client
        self.connection.sock.settimeout(0.1)

    def tearDown(self):
        self.connection.close()
        self.server.close()

    def test_send_uses_etx_framing(self):
        request_id = self.connection.send("autopa/clock", {"value": 1})
        frame = self.server.recv(4096)
        self.assertTrue(frame.endswith(ETX))
        message = json.loads(frame[:-1].decode("utf-8"))
        self.assertEqual(message["id"], request_id)
        self.assertEqual(message["method"], "autopa/clock")
        self.assertEqual(message["params"], {"value": 1})

    def test_receive_handles_multiple_and_fragmented_frames(self):
        first = json.dumps({"id": 1, "result": {}}).encode() + ETX
        second = json.dumps({
            "method": "autopa/acceleration",
            "params": {"data": [[1.0, 2.0, 3.0, 4.0]]},
        }).encode() + ETX
        self.server.sendall(first + second[:10])
        messages = self.connection.receive()
        self.assertEqual(messages, [{"id": 1, "result": {}}])
        self.server.sendall(second[10:])
        messages = self.connection.receive()
        self.assertEqual(
            messages[0]["method"], "autopa/acceleration")


class LiveStatusTest(unittest.TestCase):
    def test_supported_accelerometer_endpoints_and_optional_mode(self):
        self.assertEqual(
            "adxl345/dump_adxl345",
            ACCELEROMETER_ENDPOINTS["adxl345"])
        recorder = SynchronizedRecorder(
            "unused", "unused", "dataset",
            accelerometer_type="none")
        self.assertIsNone(recorder.accelerometer)
        self.assertFalse(
            recorder.live_status["accelerometer_config"]["enabled"])

    def test_live_status_is_atomic_and_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory, "live.json")
            recorder = SynchronizedRecorder(
                "unused", "unused", str(pathlib.Path(directory, "dataset")),
                live_status_path=str(path))
            recorder.live_started_ns = time.monotonic_ns()
            recorder.stats["force_samples"] = 260
            recorder._update_live("force", {
                "host_monotonic_ns": time.monotonic_ns(),
                "raw": 1200,
                "filtered": 1000,
            }, force_write=True)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(1000, payload["force"]["filtered"])
            self.assertGreater(payload["sample_rates_hz"]["force"], 0)
            self.assertFalse(path.with_suffix(".json.tmp").exists())
            self.assertIn("clock", payload)
            self.assertIn("extruder_motion", payload)

    def test_sample_update_does_not_write_live_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory, "live.json")
            recorder = SynchronizedRecorder(
                "unused", "unused", str(pathlib.Path(directory, "dataset")),
                live_status_path=str(path))
            recorder.live_started_ns = time.monotonic_ns()
            recorder._update_live("force", {
                "host_monotonic_ns": time.monotonic_ns(),
                "raw": 1200,
                "filtered": 1000,
            })
            self.assertFalse(path.exists())
            self.assertEqual(
                1000, recorder.live_status["force"]["filtered"])

    def test_live_force_queue_is_drained_to_latest_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory, "live.json")
            recorder = SynchronizedRecorder(
                "unused", "unused", str(pathlib.Path(directory, "dataset")),
                live_status_path=str(path))
            live_queue = queue.Queue()
            live_queue.put({
                "host_monotonic_ns": 1,
                "raw": 10,
                "filtered": 11,
                "count": 64,
            })
            live_queue.put({
                "host_monotonic_ns": 2,
                "raw": 20,
                "filtered": 21,
                "count": 128,
            })
            recorder._drain_live_force(live_queue)
            self.assertEqual(128, recorder.stats["force_samples"])
            self.assertEqual(21, recorder.live_status["force"]["filtered"])


if __name__ == "__main__":
    unittest.main()
