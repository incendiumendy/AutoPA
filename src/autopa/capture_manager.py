"""Lifecycle manager for passive, print-bound synchronized captures."""
import datetime
import glob
import os
import threading
import time

from .sync_recorder import SynchronizedRecorder


TERMINAL_PRINT_STATES = {"complete", "cancelled", "error", "standby"}


def discover_alps_device(explicit=None):
    """Return an explicit or uniquely discovered factory FLY-ALPS device."""
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    matches = sorted(glob.glob(
        "/dev/serial/by-id/"
        "usb-STMicroelectronics_PressureLeveling_*-if00"))
    return matches[0] if len(matches) == 1 else None


def _safe_name(value):
    return "".join(
        char if char.isalnum() or char in "._-" else "_"
        for char in str(value or "")).strip("._") or "print"


class CaptureManager:
    """Run one passive recorder and stop it when its print terminates."""

    def __init__(
            self, alps_device, klippy_socket, output_root, live_status_path,
            accelerometer="toolboard_t0", accelerometer_type="lis2dw",
            print_state_provider=None, max_duration=12 * 60 * 60,
            monitor_interval=1.0, recorder_factory=SynchronizedRecorder):
        self.alps_device = discover_alps_device(alps_device)
        self.klippy_socket = os.path.expanduser(klippy_socket)
        self.output_root = os.path.expanduser(output_root)
        self.live_status_path = os.path.expanduser(live_status_path)
        self.accelerometer = accelerometer
        self.accelerometer_type = accelerometer_type
        self.print_state_provider = print_state_provider
        self.max_duration = float(max_duration)
        self.monitor_interval = float(monitor_interval)
        self.recorder_factory = recorder_factory
        self.lock = threading.RLock()
        self.thread = None
        self.monitor_thread = None
        self.recorder = None
        self.state = "idle"
        self.dataset = None
        self.error = None
        self.monitor_error = None
        self.stop_reason = None
        self.attached_to_print = False
        self.seen_printing = False
        self.manifest = None

    def _active(self):
        return self.state in {"starting", "capturing", "stopping"}

    def _next_output_dir(self, name):
        stamp = datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = "%s_%s" % (stamp, _safe_name(name))
        candidate = os.path.join(self.output_root, base)
        suffix = 2
        while os.path.exists(candidate):
            candidate = os.path.join(
                self.output_root, "%s_%d" % (base, suffix))
            suffix += 1
        return candidate

    def start(self, print_state, name="print"):
        if print_state != "printing":
            raise RuntimeError(
                "Messung kann nur bei Klipper-Status 'printing' starten")
        if not self.alps_device:
            raise RuntimeError(
                "FLY-ALPS wurde nicht eindeutig gefunden; "
                "AUTOPA_ALPS_DEVICE konfigurieren")
        with self.lock:
            if self._active():
                raise RuntimeError("Eine AutoPA-Messung läuft bereits")
            output_dir = self._next_output_dir(name)
            self.recorder = self.recorder_factory(
                self.alps_device,
                self.klippy_socket,
                output_dir,
                self.accelerometer,
                self.live_status_path,
                self.accelerometer_type)
            self.state = "starting"
            self.dataset = os.path.basename(output_dir)
            self.error = None
            self.monitor_error = None
            self.stop_reason = None
            self.attached_to_print = True
            self.seen_printing = True
            self.manifest = None
            self.thread = threading.Thread(
                target=self._run_capture,
                name="autopa-managed-capture",
                daemon=True)
            self.monitor_thread = threading.Thread(
                target=self._monitor_print,
                name="autopa-print-monitor",
                daemon=True)
            self.thread.start()
            self.monitor_thread.start()
        return self.status()

    def _run_capture(self):
        with self.lock:
            if self.state == "starting":
                self.state = "capturing"
            recorder = self.recorder
        try:
            manifest = recorder.run(self.max_duration)
            with self.lock:
                self.manifest = manifest
                self.state = "complete"
                if not self.stop_reason:
                    self.stop_reason = "duration_limit"
        except Exception as exc:
            with self.lock:
                self.error = repr(exc)
                self.state = "error"
        finally:
            with self.lock:
                self.recorder = None

    def _monitor_print(self):
        while True:
            with self.lock:
                if not self._active():
                    return
            try:
                state = (
                    self.print_state_provider()
                    if self.print_state_provider else None)
                with self.lock:
                    self.monitor_error = None
                    if state == "printing":
                        self.seen_printing = True
                    should_stop = (
                        self.seen_printing
                        and state in TERMINAL_PRINT_STATES)
                if should_stop:
                    self.stop("print_finished")
                    return
            except Exception as exc:
                # Losing the read-only monitor never pauses or cancels a print.
                # The recorder continues and its own maximum duration remains
                # the final bound.
                with self.lock:
                    self.monitor_error = repr(exc)
            time.sleep(self.monitor_interval)

    def stop(self, reason="user"):
        with self.lock:
            if not self._active():
                return self.status()
            self.stop_reason = reason
            self.state = "stopping"
            recorder = self.recorder
            if recorder is not None:
                recorder.stop_event.set()
        return self.status()

    def shutdown(self):
        self.stop("service_stopping")
        thread = self.thread
        if thread and thread.is_alive():
            thread.join(5.0)

    def status(self):
        with self.lock:
            active = self._active()
            stats = (
                dict((self.manifest or {}).get("stats", {}))
                if self.manifest else None)
            return {
                "state": self.state,
                "active": active,
                "canStart": bool(self.alps_device) and not active,
                "canStop": active,
                "dataset": self.dataset,
                "attachedToPrint": self.attached_to_print,
                "stopReason": self.stop_reason,
                "error": self.error,
                "monitorError": self.monitor_error,
                "stats": stats,
                "printerAction": "none",
            }
