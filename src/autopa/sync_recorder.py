"""Capture factory FLY-ALPS and Klipper LIS2DW data in one dataset."""
import argparse
import csv
import datetime
import json
import multiprocessing
import os
import queue
import socket
import threading
import time

from .alps_serial import AlpsSerial


ETX = b"\x03"
ACCELEROMETER_ENDPOINTS = {
    "lis2dw": "lis2dw/dump_lis2dw",
    "lis3dh": "lis2dw/dump_lis2dw",
    "adxl345": "adxl345/dump_adxl345",
    "mpu9250": "mpu9250/dump_mpu9250",
}


def _record_alps_process(device, output_path, duration, stop_event,
                         ready_event, result_queue, live_queue):
    count = 0
    version = None
    try:
        with AlpsSerial(device) as alps, open(
                output_path, "w", newline="",
                buffering=1024 * 1024) as handle:
            writer = csv.writer(handle)
            writer.writerow(("host_monotonic_ns", "raw", "filtered"))
            version = alps.detect_version()
            alps.start_stream()
            ready_event.set()
            for sample in alps.samples(duration):
                writer.writerow((
                    sample.host_monotonic_ns, sample.raw, sample.filtered))
                count += 1
                if count % 64 == 0:
                    payload = {
                        "host_monotonic_ns": sample.host_monotonic_ns,
                        "raw": sample.raw,
                        "filtered": sample.filtered,
                        "count": count,
                    }
                    try:
                        live_queue.put_nowait(payload)
                    except queue.Full:
                        try:
                            live_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            live_queue.put_nowait(payload)
                        except queue.Full:
                            pass
                if stop_event.is_set():
                    break
        result_queue.put({
            "version": version,
            "count": count,
            "error": None,
        })
    except Exception as exc:
        ready_event.set()
        stop_event.set()
        result_queue.put({
            "version": version,
            "count": count,
            "error": repr(exc),
        })


class KlippyConnection:
    def __init__(self, path):
        self.path = path
        self.sock = None
        self.buffer = bytearray()
        self.next_id = 1

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.path)
        self.sock.settimeout(0.25)

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def send(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        payload = {
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        self.sock.sendall(json.dumps(payload).encode("utf-8") + ETX)
        return request_id

    def receive(self):
        try:
            chunk = self.sock.recv(65536)
        except socket.timeout:
            return []
        if not chunk:
            raise ConnectionError("Klippy socket closed")
        self.buffer.extend(chunk)
        messages = []
        while ETX in self.buffer:
            frame, _, rest = self.buffer.partition(ETX)
            self.buffer = bytearray(rest)
            if frame:
                messages.append(json.loads(frame.decode("utf-8")))
        return messages


class SynchronizedRecorder:
    def __init__(self, alps_device, klippy_socket, output_dir,
                 accelerometer="toolboard_t0", live_status_path=None,
                 accelerometer_type="lis2dw"):
        if accelerometer_type not in (*ACCELEROMETER_ENDPOINTS, "none"):
            raise ValueError(
                "Unsupported accelerometer type: %s" % accelerometer_type)
        self.alps_device = alps_device
        self.klippy_socket = klippy_socket
        self.output_dir = output_dir
        self.accelerometer_type = accelerometer_type
        self.accelerometer = (
            None if accelerometer_type == "none" else accelerometer)
        self.live_status_path = live_status_path
        self.errors = queue.Queue()
        self.stop_event = multiprocessing.Event()
        self.live_lock = threading.Lock()
        self.live_last_write_ns = 0
        self.live_started_ns = None
        self.stats = {"force_samples": 0, "acceleration_samples": 0,
                      "acceleration_errors": 0,
                      "acceleration_overflows": 0,
                      "extruder_motion_segments": 0,
                      "printer_status_updates": 0}
        self.alps_version = None
        self.live_status = {
            "format_version": 1,
            "state": "starting",
            "dataset": os.path.basename(output_dir),
            "accelerometer_config": {
                "enabled": self.accelerometer is not None,
                "type": self.accelerometer_type,
                "name": self.accelerometer,
            },
            "updated_host_monotonic_ns": None,
            "force": None,
            "acceleration": None,
            "printer": None,
            "clock": None,
            "extruder_motion": {
                "segments": [],
            },
        }

    def _update_live(self, section=None, payload=None, force_write=False):
        if not self.live_status_path:
            return
        now_ns = time.monotonic_ns()
        with self.live_lock:
            if section:
                self.live_status[section] = payload
            self.live_status["updated_host_monotonic_ns"] = now_ns
            if not force_write and now_ns - self.live_last_write_ns < 100_000_000:
                return
            if not force_write:
                return
            elapsed = max(
                (now_ns - (self.live_started_ns or now_ns)) / 1e9, 0.001)
            self.live_status["sample_rates_hz"] = {
                "force": self.stats["force_samples"] / elapsed,
                "acceleration": self.stats["acceleration_samples"] / elapsed,
            }
            temporary_path = self.live_status_path + ".tmp"
            parent = os.path.dirname(self.live_status_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(self.live_status, handle, sort_keys=True)
                handle.write("\n")
            os.replace(temporary_path, self.live_status_path)
            self.live_last_write_ns = now_ns

    def _drain_live_force(self, live_queue):
        latest = None
        while True:
            try:
                latest = live_queue.get_nowait()
            except queue.Empty:
                break
        if latest:
            self.stats["force_samples"] = latest.pop("count")
            self._update_live("force", latest)

    def _publish_live(self, duration, live_queue):
        started = time.monotonic()
        while (not self.stop_event.wait(0.1)
               and time.monotonic() - started < duration):
            self._drain_live_force(live_queue)
            self._update_live(force_write=True)

    def _record_alps(self, duration, ready_event):
        try:
            path = os.path.join(self.output_dir, "force.csv")
            with AlpsSerial(self.alps_device) as alps, open(
                    path, "w", newline="", buffering=1024 * 1024) as handle:
                writer = csv.writer(handle)
                writer.writerow(("host_monotonic_ns", "raw", "filtered"))
                self.alps_version = alps.detect_version()
                alps.start_stream()
                ready_event.set()
                for sample in alps.samples(duration):
                    writer.writerow((
                        sample.host_monotonic_ns, sample.raw, sample.filtered))
                    self.stats["force_samples"] += 1
                    self._update_live("force", {
                        "host_monotonic_ns": sample.host_monotonic_ns,
                        "raw": sample.raw,
                        "filtered": sample.filtered,
                    })
                    if self.stop_event.is_set():
                        break
        except Exception as exc:
            self.errors.put(("alps", repr(exc)))
            ready_event.set()
            self.stop_event.set()

    def _record_klippy(self, duration, ready_event):
        connection = KlippyConnection(self.klippy_socket)
        try:
            connection.connect()
            accel_path = os.path.join(
                self.output_dir, "acceleration.csv")
            batches_path = os.path.join(
                self.output_dir, "acceleration_batches.csv")
            clocks_path = os.path.join(self.output_dir, "clock_sync.csv")
            events_path = os.path.join(self.output_dir, "events.csv")
            extruder_path = os.path.join(
                self.output_dir, "extruder_motion.csv")
            status_path = os.path.join(
                self.output_dir, "printer_status.csv")
            with open(accel_path, "w", newline="",
                      buffering=1024 * 1024) as accel_handle, open(
                    batches_path, "w", newline="",
                    buffering=1024 * 1024) as batches_handle, open(
                    clocks_path, "w", newline="",
                    buffering=1024 * 1024) as clocks_handle, open(
                    events_path, "w", newline="",
                    buffering=1024 * 1024) as events_handle, open(
                    extruder_path, "w", newline="",
                    buffering=1024 * 1024) as extruder_handle, open(
                    status_path, "w", newline="",
                    buffering=1024 * 1024) as status_handle:
                accel_writer = csv.writer(accel_handle)
                batch_writer = csv.writer(batches_handle)
                clock_writer = csv.writer(clocks_handle)
                events_writer = csv.writer(events_handle)
                extruder_writer = csv.writer(extruder_handle)
                status_writer = csv.writer(status_handle)
                accel_writer.writerow((
                    "print_time", "x_mm_s2", "y_mm_s2", "z_mm_s2"))
                batch_writer.writerow((
                    "host_monotonic_ns", "samples", "errors", "overflows"))
                clock_writer.writerow((
                    "request_host_monotonic_ns", "response_host_monotonic_ns",
                    "klipper_host_monotonic", "print_time"))
                events_writer.writerow((
                    "sequence", "print_time", "host_monotonic",
                    "event", "value"))
                extruder_writer.writerow((
                    "print_time", "duration_s",
                    "start_velocity_mm_s", "acceleration_mm_s2",
                    "start_position_mm", "direction",
                    "pressure_advance_active"))
                status_writer.writerow((
                    "host_monotonic_ns", "eventtime",
                    "extruder_temperature_c", "extruder_target_c",
                    "pressure_advance", "smooth_time", "print_state"))
                if self.accelerometer is not None:
                    connection.send(
                        ACCELEROMETER_ENDPOINTS[self.accelerometer_type], {
                            "sensor": self.accelerometer,
                            "response_template": {
                                "method": "autopa/acceleration"},
                        })
                connection.send("motion_report/dump_trapq", {
                    "name": "extruder",
                    "response_template": {
                        "method": "autopa/extruder_motion"},
                })
                status_subscription_id = connection.send(
                    "objects/subscribe", {
                        "objects": {
                            "extruder": [
                                "temperature", "target",
                                "pressure_advance", "smooth_time"],
                            "print_stats": ["state"],
                        },
                        "response_template": {
                            "method": "autopa/printer_status"},
                    })
                printer_status = {}

                def record_printer_status(params):
                    for object_name, update in params.get(
                            "status", {}).items():
                        printer_status.setdefault(
                            object_name, {}).update(update)
                    extruder = printer_status.get("extruder", {})
                    print_stats = printer_status.get("print_stats", {})
                    status_writer.writerow((
                        time.monotonic_ns(), params.get("eventtime"),
                        extruder.get("temperature"),
                        extruder.get("target"),
                        extruder.get("pressure_advance"),
                        extruder.get("smooth_time"),
                        print_stats.get("state")))
                    self.stats["printer_status_updates"] += 1
                    self._update_live("printer", {
                        "eventtime": params.get("eventtime"),
                        "temperature_c": extruder.get("temperature"),
                        "target_c": extruder.get("target"),
                        "pressure_advance": extruder.get("pressure_advance"),
                        "smooth_time": extruder.get("smooth_time"),
                        "print_state": print_stats.get("state"),
                    })
                pending_clock = {}
                pending_events = {}
                event_sequence = -1
                request_ns = time.monotonic_ns()
                clock_id = connection.send("autopa/clock")
                pending_clock[clock_id] = request_ns
                events_id = connection.send(
                    "autopa/events", {"after": event_sequence})
                pending_events[events_id] = True
                ready_event.set()
                started = time.monotonic()
                next_clock = started + 1.0
                next_events = started + 0.1
                while (not self.stop_event.is_set()
                       and time.monotonic() - started < duration):
                    for message in connection.receive():
                        if message.get("method") == "autopa/acceleration":
                            params = message.get("params", {})
                            data = params.get("data", ())
                            accel_writer.writerows(data)
                            self.stats["acceleration_samples"] += len(data)
                            errors = params.get("errors", 0)
                            overflows = params.get("overflows", 0)
                            self.stats["acceleration_errors"] = max(
                                self.stats["acceleration_errors"], errors)
                            self.stats["acceleration_overflows"] = max(
                                self.stats["acceleration_overflows"], overflows)
                            if data:
                                latest = data[-1]
                                self._update_live("acceleration", {
                                    "print_time": latest[0],
                                    "x_mm_s2": latest[1],
                                    "y_mm_s2": latest[2],
                                    "z_mm_s2": latest[3],
                                    "errors": errors,
                                    "overflows": overflows,
                                })
                            batch_writer.writerow((
                                time.monotonic_ns(), len(data),
                                errors, overflows))
                        if message.get("method") == "autopa/extruder_motion":
                            params = message.get("params", {})
                            live_segments = []
                            for segment in params.get("data", ()):
                                start_position = segment[4]
                                direction = segment[5]
                                extruder_writer.writerow((
                                    segment[0], segment[1],
                                    segment[2], segment[3],
                                    start_position[0], direction[0],
                                    direction[1]))
                                self.stats[
                                    "extruder_motion_segments"] += 1
                                live_segments.append({
                                    "print_time": segment[0],
                                    "duration_s": segment[1],
                                    "start_velocity_mm_s": segment[2],
                                    "acceleration_mm_s2": segment[3],
                                    "direction": direction[0],
                                    "pressure_advance_active": direction[1],
                                })
                            if live_segments:
                                current = (
                                    self.live_status.get(
                                        "extruder_motion", {})
                                    .get("segments", []))
                                self._update_live("extruder_motion", {
                                    "segments":
                                        (current + live_segments)[-96:],
                                })
                        if message.get("method") == "autopa/printer_status":
                            record_printer_status(
                                message.get("params", {}))
                        request_id = message.get("id")
                        if request_id == status_subscription_id:
                            record_printer_status(
                                message.get("result", {}))
                        if request_id in pending_clock:
                            response_ns = time.monotonic_ns()
                            result = message.get("result", {})
                            clock_writer.writerow((
                                pending_clock.pop(request_id), response_ns,
                                result.get("host_monotonic"),
                                result.get("print_time")))
                            self._update_live("clock", {
                                "host_monotonic":
                                    result.get("host_monotonic"),
                                "print_time": result.get("print_time"),
                                "response_host_monotonic_ns": response_ns,
                            })
                        if request_id in pending_events:
                            pending_events.pop(request_id)
                            result = message.get("result", {})
                            for event in result.get("events", ()):
                                events_writer.writerow((
                                    event.get("sequence"),
                                    event.get("print_time"),
                                    event.get("host_monotonic"),
                                    event.get("event"),
                                    event.get("value")))
                            event_sequence = result.get(
                                "last_sequence", event_sequence)
                        if "error" in message:
                            raise RuntimeError(
                                "Klippy API error: %s" % message["error"])
                    now = time.monotonic()
                    if now >= next_clock:
                        request_ns = time.monotonic_ns()
                        clock_id = connection.send("autopa/clock")
                        pending_clock[clock_id] = request_ns
                        next_clock = now + 1.0
                    if now >= next_events and not pending_events:
                        events_id = connection.send(
                            "autopa/events", {"after": event_sequence})
                        pending_events[events_id] = True
                        next_events = now + 0.1
        except Exception as exc:
            self.errors.put(("klippy", repr(exc)))
            ready_event.set()
            self.stop_event.set()
        finally:
            connection.close()

    def run(self, duration):
        os.makedirs(self.output_dir)
        self.live_started_ns = time.monotonic_ns()
        self.live_status["state"] = "capturing"
        self._update_live(force_write=True)
        alps_ready = multiprocessing.Event()
        klippy_ready = threading.Event()
        alps_result_queue = multiprocessing.Queue()
        alps_live_queue = multiprocessing.Queue(maxsize=8)
        alps_process = multiprocessing.Process(
            target=_record_alps_process,
            args=(
                self.alps_device,
                os.path.join(self.output_dir, "force.csv"),
                duration, self.stop_event, alps_ready,
                alps_result_queue, alps_live_queue),
            name="autopa-alps", daemon=True)
        threads = [
            threading.Thread(
                target=self._record_klippy, args=(duration, klippy_ready),
                name="autopa-klippy", daemon=True),
        ]
        live_thread = threading.Thread(
            target=self._publish_live, args=(duration, alps_live_queue),
            name="autopa-live", daemon=True)
        alps_process.start()
        for thread in threads:
            thread.start()
        live_thread.start()
        alps_ready.wait(3.0)
        klippy_ready.wait(3.0)
        alps_process.join(duration + 3.0)
        for thread in threads:
            thread.join(duration + 3.0)
        self.stop_event.set()
        for thread in threads:
            thread.join(2.0)
        live_thread.join(2.0)
        self._drain_live_force(alps_live_queue)
        if alps_process.is_alive():
            self.errors.put(("alps", "ALPS process did not stop"))
            alps_process.terminate()
            alps_process.join(2.0)
        try:
            alps_result = alps_result_queue.get(timeout=1.0)
        except queue.Empty:
            alps_result = {
                "version": None,
                "count": self.stats["force_samples"],
                "error": "ALPS process returned no result",
            }
        self.alps_version = alps_result.get("version")
        self.stats["force_samples"] = alps_result.get("count", 0)
        if alps_result.get("error"):
            self.errors.put(("alps", alps_result["error"]))
        errors = []
        while not self.errors.empty():
            errors.append(self.errors.get())
        self.live_status["state"] = "error" if errors else "complete"
        self.live_status["errors"] = errors
        self._update_live(force_write=True)
        manifest = {
            "format_version": 1,
            "created_utc":
                datetime.datetime.utcnow().isoformat() + "Z",
            "duration_seconds": duration,
            "alps_device": self.alps_device,
            "alps_firmware": self.alps_version,
            "accelerometer": self.accelerometer,
            "accelerometer_type": self.accelerometer_type,
            "accelerometer_enabled": self.accelerometer is not None,
            "extruder_motion_source": "motion_report/dump_trapq:extruder",
            "stats": self.stats,
            "errors": errors,
            "policy": {
                "printer_control": "none",
                "on_capture_error": "stop_capture_only",
                "on_bad_data": "reject_dataset_after_capture",
                "may_pause_or_cancel_print": False,
            },
        }
        with open(os.path.join(self.output_dir, "manifest.json"), "w") as file:
            json.dump(manifest, file, indent=2, sort_keys=True)
            file.write("\n")
        if errors:
            raise RuntimeError("Capture failed: %s" % (errors,))
        return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Synchronously capture FLY-ALPS and optional motion data")
    parser.add_argument("--alps-device", required=True)
    parser.add_argument(
        "--klippy-socket",
        default=os.path.expanduser("~/printer_data/comms/klippy.sock"))
    parser.add_argument("--accelerometer", default="toolboard_t0")
    parser.add_argument(
        "--accelerometer-type",
        choices=(*ACCELEROMETER_ENDPOINTS, "none"),
        default="lis2dw",
        help=("Klipper accelerometer driver, or 'none' for a force-only "
              "capture"))
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--output-root",
                        default=os.path.expanduser("~/printer_data/autopa"))
    parser.add_argument(
        "--live-status",
        help=("Atomic dashboard status file; defaults to "
              "<output-root>/live.json"))
    parser.add_argument("--name", default="capture")
    args = parser.parse_args()
    stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_name = "".join(
        char if char.isalnum() or char in "._-" else "_"
        for char in args.name).strip("._") or "capture"
    output_dir = os.path.join(
        args.output_root, "%s_%s" % (stamp, safe_name))
    live_status_path = (
        os.path.expanduser(args.live_status) if args.live_status
        else os.path.join(args.output_root, "live.json"))
    recorder = SynchronizedRecorder(
        args.alps_device, args.klippy_socket, output_dir,
        args.accelerometer, live_status_path, args.accelerometer_type)
    manifest = recorder.run(args.duration)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
