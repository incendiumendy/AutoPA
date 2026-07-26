# Synchronized FLY-ALPS and LIS2DW capture for Klipper
#
# Copyright (C) 2026 AutoPA contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import csv
import datetime
import json
import logging
import os
import re


class AutoPACapture:
    cmd_AUTOPA_CAPTURE_START_help = "Start synchronized ALPS and LIS2DW capture"
    cmd_AUTOPA_CAPTURE_MARK_help = "Add a print-time marker to the capture"
    cmd_AUTOPA_CAPTURE_STOP_help = "Stop capture and close the dataset"
    cmd_AUTOPA_CAPTURE_STATUS_help = "Report capture state and sample counters"

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.load_cell_name = config.get("load_cell", "alps")
        self.accel_name = config.get("accelerometer", "toolboard_t0")
        default_dir = os.path.expanduser("~/printer_data/autopa")
        self.data_dir = os.path.expanduser(config.get("data_dir", default_dir))
        self.active = False
        self.session_dir = None
        self.files = {}
        self.writers = {}
        self.force_samples = 0
        self.accel_samples = 0
        self.force_errors = 0
        self.force_overflows = 0
        self.accel_errors = 0
        self.accel_overflows = 0
        self.generation = 0
        self.load_cell = None
        self.load_sensor = None
        self.accelerometer = None
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler(
            "klippy:disconnect", self._handle_disconnect)
        gcode = self.printer.lookup_object("gcode")
        gcode.register_command(
            "AUTOPA_CAPTURE_START", self.cmd_AUTOPA_CAPTURE_START,
            desc=self.cmd_AUTOPA_CAPTURE_START_help)
        gcode.register_command(
            "AUTOPA_CAPTURE_MARK", self.cmd_AUTOPA_CAPTURE_MARK,
            desc=self.cmd_AUTOPA_CAPTURE_MARK_help)
        gcode.register_command(
            "AUTOPA_CAPTURE_STOP", self.cmd_AUTOPA_CAPTURE_STOP,
            desc=self.cmd_AUTOPA_CAPTURE_STOP_help)
        gcode.register_command(
            "AUTOPA_CAPTURE_STATUS", self.cmd_AUTOPA_CAPTURE_STATUS,
            desc=self.cmd_AUTOPA_CAPTURE_STATUS_help)

    def _handle_ready(self):
        self.load_cell = self.printer.lookup_object(
            "load_cell " + self.load_cell_name)
        self.load_sensor = self.load_cell.get_sensor()
        self.accelerometer = self.printer.lookup_object(
            "lis2dw " + self.accel_name)
        if not hasattr(self.load_sensor, "add_client"):
            raise self.printer.config_error(
                "AutoPA load-cell sensor has no bulk client interface")
        if not hasattr(self.accelerometer, "batch_bulk"):
            raise self.printer.config_error(
                "AutoPA accelerometer has no bulk client interface")

    def _handle_disconnect(self):
        if self.active:
            self._finish("klippy_disconnect")

    def _safe_name(self, value):
        value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
        return value.strip("._") or "capture"

    def _open_csv(self, key, filename, header):
        path = os.path.join(self.session_dir, filename)
        handle = open(path, "w", newline="", buffering=1024 * 1024)
        writer = csv.writer(handle)
        writer.writerow(header)
        self.files[key] = handle
        self.writers[key] = writer

    def _current_print_time(self):
        eventtime = self.reactor.monotonic()
        return self.load_sensor.get_mcu().estimated_print_time(eventtime)

    def _write_manifest(self, stopped_reason=None):
        eventtime = self.reactor.monotonic()
        manifest = {
            "format_version": 1,
            "session": os.path.basename(self.session_dir),
            "active": self.active,
            "load_cell": self.load_cell_name,
            "accelerometer": self.accel_name,
            "started_utc": self.started_utc,
            "stopped_utc": (
                datetime.datetime.utcnow().isoformat() + "Z"
                if stopped_reason is not None else None),
            "stopped_reason": stopped_reason,
            "sample_counts": {
                "force": self.force_samples,
                "acceleration": self.accel_samples,
            },
            "errors": {
                "force": self.force_errors,
                "acceleration": self.accel_errors,
            },
            "overflows": {
                "force": self.force_overflows,
                "acceleration": self.accel_overflows,
            },
            "sensor_status": {
                "force": self.load_sensor.get_status(eventtime),
                "acceleration": {
                    "errors": self.accelerometer.last_error_count,
                    "overflows":
                        self.accelerometer.ffreader.get_last_overflows(),
                    "sample_rate": self.accelerometer.data_rate,
                },
            },
        }
        path = os.path.join(self.session_dir, "manifest.json")
        with open(path, "w") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")

    def _force_batch(self, generation, msg):
        if not self.active or generation != self.generation:
            return False
        data = msg.get("data", ())
        self.writers["force"].writerows(data)
        self.force_samples += len(data)
        self.force_errors = max(self.force_errors, msg.get("errors", 0))
        self.force_overflows = max(
            self.force_overflows, msg.get("overflows", 0))
        self.writers["force_batches"].writerow((
            self.reactor.monotonic(), len(data), msg.get("errors", 0),
            msg.get("overflows", 0)))
        return True

    def _accel_batch(self, generation, msg):
        if not self.active or generation != self.generation:
            return False
        data = msg.get("data", ())
        self.writers["acceleration"].writerows(data)
        self.accel_samples += len(data)
        self.accel_errors = max(self.accel_errors, msg.get("errors", 0))
        self.accel_overflows = max(
            self.accel_overflows, msg.get("overflows", 0))
        self.writers["accel_batches"].writerow((
            self.reactor.monotonic(), len(data), msg.get("errors", 0),
            msg.get("overflows", 0)))
        return True

    def _finish(self, reason):
        if not self.active:
            return
        self.active = False
        self.writers["events"].writerow((
            self._current_print_time(), self.reactor.monotonic(),
            "capture_stop", reason))
        for handle in self.files.values():
            handle.flush()
            os.fsync(handle.fileno())
        self._write_manifest(reason)
        for handle in self.files.values():
            handle.close()
        self.files = {}
        self.writers = {}
        logging.info("AutoPA capture stopped: %s", self.session_dir)

    def cmd_AUTOPA_CAPTURE_START(self, gcmd):
        if self.active:
            raise gcmd.error("AutoPA capture is already active")
        if self.load_sensor is None or self.accelerometer is None:
            raise gcmd.error("AutoPA sensors are not ready")
        label = self._safe_name(gcmd.get("NAME", "capture"))
        stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        os.makedirs(self.data_dir, exist_ok=True)
        self.session_dir = os.path.join(
            self.data_dir, "%s_%s" % (stamp, label))
        os.makedirs(self.session_dir)
        self.started_utc = datetime.datetime.utcnow().isoformat() + "Z"
        self.force_samples = self.accel_samples = 0
        self.force_errors = self.accel_errors = 0
        self.force_overflows = self.accel_overflows = 0
        self.generation += 1
        self._open_csv(
            "force", "force.csv",
            ("print_time", "counts", "normalized"))
        self._open_csv(
            "acceleration", "acceleration.csv",
            ("print_time", "x_mm_s2", "y_mm_s2", "z_mm_s2"))
        self._open_csv(
            "events", "events.csv",
            ("print_time", "host_monotonic", "event", "value"))
        self._open_csv(
            "force_batches", "force_batches.csv",
            ("host_monotonic", "samples", "errors", "overflows"))
        self._open_csv(
            "accel_batches", "acceleration_batches.csv",
            ("host_monotonic", "samples", "errors", "overflows"))
        self.active = True
        self.writers["events"].writerow((
            self._current_print_time(), self.reactor.monotonic(),
            "capture_start", label))
        generation = self.generation
        self.load_sensor.add_client(
            lambda msg: self._force_batch(generation, msg))
        self.accelerometer.batch_bulk.add_client(
            lambda msg: self._accel_batch(generation, msg))
        self._write_manifest()
        gcmd.respond_info("AutoPA capture started: %s" % (self.session_dir,))

    def cmd_AUTOPA_CAPTURE_MARK(self, gcmd):
        if not self.active:
            raise gcmd.error("AutoPA capture is not active")
        event = self._safe_name(gcmd.get("EVENT"))
        value = gcmd.get("VALUE", "")
        # The last queued move time aligns a marker following a G-code move
        # with that move, while host_monotonic records command arrival.
        toolhead = self.printer.lookup_object("toolhead")
        self.writers["events"].writerow((
            toolhead.get_last_move_time(), self.reactor.monotonic(),
            event, value))

    def cmd_AUTOPA_CAPTURE_STOP(self, gcmd):
        if not self.active:
            raise gcmd.error("AutoPA capture is not active")
        path = self.session_dir
        self._finish("gcode")
        gcmd.respond_info(
            "AutoPA capture stopped: %s (%d force, %d acceleration samples)"
            % (path, self.force_samples, self.accel_samples))

    def cmd_AUTOPA_CAPTURE_STATUS(self, gcmd):
        if not self.active:
            gcmd.respond_info("AutoPA capture is inactive")
            return
        gcmd.respond_info(
            "AutoPA capture active: %s (%d force, %d acceleration samples)"
            % (self.session_dir, self.force_samples, self.accel_samples))

    def get_status(self, eventtime):
        return {
            "active": self.active,
            "session_dir": self.session_dir if self.active else None,
            "force_samples": self.force_samples,
            "acceleration_samples": self.accel_samples,
            "force_errors": self.force_errors,
            "acceleration_errors": self.accel_errors,
            "force_overflows": self.force_overflows,
            "acceleration_overflows": self.accel_overflows,
        }


def load_config(config):
    return AutoPACapture(config)
