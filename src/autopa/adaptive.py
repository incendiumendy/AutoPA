"""Bounded, opt-in live PA and firmware-retraction validation controller."""
import argparse
import collections
import json
import math
import os
import statistics
import threading
import time
import urllib.error
import urllib.request

from .gcode_context import ContextTimeline


ARM_PHRASE = "AUTOPA VALIDIEREN"
CONTROL_MODES = {"off", "dry_run", "apply"}
DEFAULT_CONFIG = {
    "mode": "off",
    "adaptive_pa_enabled": False,
    "auto_retract_enabled": False,
    "pa_min": 0.0,
    "pa_max": 0.12,
    "pa_step": 0.002,
    "pa_max_total_delta": 0.01,
    "retract_min_mm": 0.2,
    "retract_max_mm": 1.5,
    "retract_step_mm": 0.05,
    "retract_max_total_delta_mm": 0.30,
    "min_update_interval_s": 30.0,
    "min_pa_windows": 5,
    "min_retract_events": 5,
    "max_force_age_s": 0.5,
    "min_force_rate_hz": 1000.0,
    "max_acceleration_mm_s2": 50000.0,
    "temperature_tolerance_c": 2.0,
    "filament_diameter_mm": 1.75,
}

BOOLEAN_CONFIG_KEYS = {
    "adaptive_pa_enabled",
    "auto_retract_enabled",
}
INTEGER_CONFIG_RANGES = {
    "min_pa_windows": (3, 100),
    "min_retract_events": (3, 100),
}
NUMBER_CONFIG_RANGES = {
    "pa_min": (0.0, 0.20),
    "pa_max": (0.0, 0.20),
    "pa_step": (0.0001, 0.02),
    "pa_max_total_delta": (0.0001, 0.05),
    "retract_min_mm": (0.0, 5.0),
    "retract_max_mm": (0.05, 10.0),
    "retract_step_mm": (0.01, 0.50),
    "retract_max_total_delta_mm": (0.01, 1.0),
    "min_update_interval_s": (10.0, 600.0),
    "max_force_age_s": (0.05, 5.0),
    "min_force_rate_hz": (100.0, 50000.0),
    "max_acceleration_mm_s2": (1000.0, 200000.0),
    "temperature_tolerance_c": (0.5, 15.0),
    "filament_diameter_mm": (1.0, 3.0),
}


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _median(values):
    return statistics.median(values) if values else None


def _mad(values, center=None):
    if not values:
        return None
    center = _median(values) if center is None else center
    return _median([abs(value - center) for value in values])


def _correlation(left, right):
    if len(left) != len(right) or len(left) < 8:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_delta)
        * sum(value * value for value in right_delta))
    if denominator <= 1e-12:
        return None
    return sum(
        a * b for a, b in zip(left_delta, right_delta)) / denominator


def validated_config(current, values):
    """Validate a complete control update against conservative hard limits."""
    unknown = set(values) - set(DEFAULT_CONFIG)
    if unknown:
        raise ValueError(
            "unknown control setting: %s" % sorted(unknown)[0])
    candidate = dict(current)
    candidate.update(values)
    mode = candidate.get("mode")
    if mode not in CONTROL_MODES:
        raise ValueError("invalid control mode")
    if mode == "apply":
        raise ValueError("apply mode requires transient arming")
    for key in BOOLEAN_CONFIG_KEYS:
        if not isinstance(candidate.get(key), bool):
            raise ValueError("%s must be a boolean" % key)
    for key, limits in INTEGER_CONFIG_RANGES.items():
        value = candidate.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("%s must be an integer" % key)
        if not limits[0] <= value <= limits[1]:
            raise ValueError("%s is outside the safe range" % key)
    for key, limits in NUMBER_CONFIG_RANGES.items():
        value = candidate.get(key)
        if isinstance(value, bool) or not _finite(value):
            raise ValueError("%s must be a finite number" % key)
        value = float(value)
        if not limits[0] <= value <= limits[1]:
            raise ValueError("%s is outside the safe range" % key)
        candidate[key] = value
    if candidate["pa_min"] >= candidate["pa_max"]:
        raise ValueError("pa_min must be smaller than pa_max")
    if candidate["retract_min_mm"] >= candidate["retract_max_mm"]:
        raise ValueError(
            "retract_min_mm must be smaller than retract_max_mm")
    return candidate


def best_pressure_lag(velocities, pressures, max_lag_samples=3):
    """Return sample lag where positive means pressure follows extrusion."""
    best = None
    for lag in range(-max_lag_samples, max_lag_samples + 1):
        if lag > 0:
            left = velocities[:-lag]
            right = pressures[lag:]
        elif lag < 0:
            left = velocities[-lag:]
            right = pressures[:lag]
        else:
            left = velocities
            right = pressures
        score = _correlation(left, right)
        if score is None:
            continue
        candidate = (score, -abs(lag), lag)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return None
    return {"correlation": best[0], "lag_samples": best[2]}


def extruder_velocity_from_live(live, now_monotonic_ns=None):
    clock = live.get("clock") or {}
    motion = live.get("extruder_motion") or {}
    segments = motion.get("segments") or ()
    if not segments or not _finite(clock.get("host_monotonic")):
        return None, None, False
    now_monotonic = (
        (now_monotonic_ns or time.monotonic_ns()) / 1e9)
    print_time = (
        float(clock["print_time"])
        + now_monotonic - float(clock["host_monotonic"]))
    for segment in reversed(segments):
        start = float(segment["print_time"])
        duration = float(segment["duration_s"])
        if start <= print_time <= start + duration:
            elapsed = print_time - start
            velocity = (
                float(segment["start_velocity_mm_s"])
                + float(segment["acceleration_mm_s2"]) * elapsed)
            velocity *= float(segment["direction"])
            return velocity, print_time, bool(
                segment.get("pressure_advance_active"))
    return 0.0, print_time, False


def toolhead_velocity_from_live(live, print_time):
    motion = live.get("toolhead_motion") or {}
    segments = motion.get("segments") or ()
    if not segments or not _finite(print_time):
        return None
    for segment in reversed(segments):
        start = float(segment["print_time"])
        duration = float(segment["duration_s"])
        if start <= print_time <= start + duration:
            elapsed = print_time - start
            return max(
                0.0,
                float(segment["start_velocity_mm_s"])
                + float(segment["acceleration_mm_s2"]) * elapsed)
    return 0.0


def live_sample(live, now_monotonic_ns=None):
    now_ns = now_monotonic_ns or time.monotonic_ns()
    force = live.get("force") or {}
    acceleration = live.get("acceleration") or {}
    printer = live.get("printer") or {}
    components = [
        acceleration.get("x_mm_s2"),
        acceleration.get("y_mm_s2"),
        acceleration.get("z_mm_s2"),
    ]
    magnitude = (
        math.sqrt(sum(float(value) ** 2 for value in components))
        if all(_finite(value) for value in components) else None)
    velocity, print_time, pa_active = extruder_velocity_from_live(
        live, now_ns)
    toolhead_velocity = toolhead_velocity_from_live(live, print_time)
    force_ns = force.get("host_monotonic_ns")
    force_age = (
        max(0.0, (now_ns - force_ns) / 1e9)
        if isinstance(force_ns, int) else None)
    return {
        "host_monotonic": now_ns / 1e9,
        "print_time": print_time,
        "force": force.get("filtered"),
        "force_raw": force.get("raw"),
        "force_age_s": force_age,
        "force_rate_hz": (
            (live.get("sample_rates_hz") or {}).get("force")),
        "acceleration": magnitude,
        "acceleration_errors": acceleration.get("errors", 0),
        "acceleration_overflows": acceleration.get("overflows", 0),
        "accelerometer_enabled": (
            (live.get("accelerometer_config") or {}).get("enabled", True)),
        "e_velocity": velocity,
        "toolhead_velocity": toolhead_velocity,
        "pressure_advance_active": pa_active,
        "print_state": printer.get("print_state"),
        "temperature": printer.get("temperature_c"),
        "target": printer.get("target_c"),
        "pressure_advance": printer.get("pressure_advance"),
    }


class AdaptiveEstimator:
    """Conservative streaming estimator; it never sends printer commands."""

    def __init__(self, config=None):
        self.config = dict(DEFAULT_CONFIG)
        self.config.update(config or {})
        self.baseline_values = collections.deque(maxlen=200)
        self.extrusion_deltas = collections.deque(maxlen=200)
        self.history = collections.deque(maxlen=80)
        self.pa_lags = collections.deque(maxlen=12)
        self.retract_residuals = collections.deque(maxlen=20)
        self.previous_velocity = 0.0
        self.pending_retract_at = None
        self.last_pa_evaluation = 0.0
        self.last_retract_evaluation = 0.0
        self.snapshot = {
            "pressure": {
                "raw": None, "baseline": None, "delta": None,
                "normalized": None, "unit": "counts",
            },
            "suggested_pa": None,
            "suggested_retract_mm": None,
            "pa_confidence": "waiting",
            "retract_confidence": "waiting",
            "pa_windows": 0,
            "retract_events": 0,
            "reason": "waiting_for_live_data",
            "gcode_context": {
                "active": False,
                "layer": None,
                "z_mm": None,
                "feature": "unknown",
                "object": None,
                "pa_eligible": False,
                "eligibility_reason": "context_marker_pending_or_missing",
            },
            "pa_context_eligible": False,
        }

    def update_config(self, config):
        self.config.update(config)

    def _validity_reason(self, sample):
        if not _finite(sample.get("force")):
            return "force_missing"
        if not _finite(sample.get("force_age_s")):
            return "force_timestamp_missing"
        if sample["force_age_s"] > self.config["max_force_age_s"]:
            return "force_stale"
        if (not _finite(sample.get("force_rate_hz"))
                or sample["force_rate_hz"]
                < self.config["min_force_rate_hz"]):
            return "force_rate_too_low"
        if sample.get("e_velocity") is None:
            return "extruder_motion_missing"
        if (sample.get("acceleration_errors", 0) > 0
                or sample.get("acceleration_overflows", 0) > 0):
            return "accelerometer_fault"
        acceleration = sample.get("acceleration")
        if (_finite(acceleration)
                and acceleration > self.config["max_acceleration_mm_s2"]):
            return "mechanical_disturbance"
        temperature = sample.get("temperature")
        target = sample.get("target")
        if (_finite(target) and target > 0):
            if (not _finite(temperature)
                    or abs(temperature - target)
                    > self.config["temperature_tolerance_c"]):
                return "temperature_unstable"
        return None

    def observe(self, sample, current_retract_mm=None):
        if (sample.get("e_velocity") is None
                and sample.get("print_state")
                in {"standby", "complete", "cancelled"}):
            # A confirmed idle printer has no commanded extrusion. This lets
            # a fresh live preview learn its no-flow baseline without motion
            # trapq segments, while printing and paused states still fail
            # closed when extrusion context is missing.
            sample = dict(sample)
            sample["e_velocity"] = 0.0
        now = float(sample.get("host_monotonic") or time.monotonic())
        force = sample.get("force")
        velocity = sample.get("e_velocity")
        context = sample.get("gcode_context") or {
            "active": False,
            "feature": "unknown",
            "pa_eligible": False,
            "eligibility_reason": "context_marker_pending_or_missing",
        }
        self.snapshot["gcode_context"] = dict(context)
        self.snapshot["pa_context_eligible"] = bool(
            context.get("active") and context.get("pa_eligible"))
        reason = self._validity_reason(sample)
        if reason:
            self.snapshot["reason"] = reason
            self.snapshot["pressure"]["raw"] = (
                float(force) if _finite(force) else None)
            return dict(self.snapshot)

        force = float(force)
        velocity = float(velocity)
        acceleration = sample.get("acceleration")
        quiet = (
            not _finite(acceleration)
            or acceleration < 0.25 * self.config["max_acceleration_mm_s2"])
        if abs(velocity) <= 0.02 and quiet:
            self.baseline_values.append(force)
        baseline = _median(self.baseline_values)
        if baseline is None:
            self.snapshot["reason"] = "learning_no_flow_baseline"
            self.snapshot["pressure"]["raw"] = force
            return dict(self.snapshot)

        delta = force - baseline
        if velocity >= 0.2:
            self.extrusion_deltas.append(delta)
        polarity_source = _median(self.extrusion_deltas)
        polarity = (
            1.0 if polarity_source is None or polarity_source >= 0 else -1.0)
        pressure = polarity * delta
        scale = _median([abs(value) for value in self.extrusion_deltas])
        noise = _mad(list(self.baseline_values), baseline) or 0.0
        usable_scale = max(scale or 0.0, 6.0 * noise, 1.0)
        normalized = pressure / usable_scale
        self.snapshot["pressure"] = {
            "raw": force,
            "baseline": baseline,
            "delta": delta,
            "normalized": normalized,
            "unit": "counts",
        }

        if self.snapshot["pa_context_eligible"]:
            self.history.append((now, max(0.0, velocity), normalized))
        else:
            # Never let support, bridge or unknown-feature samples leak into
            # the next eligible PA correlation window.
            self.history.clear()
        if (sample.get("print_state") == "printing"
                and self.snapshot["pa_context_eligible"]
                and len(self.history) >= 30
                and now - self.last_pa_evaluation >= 4.0):
            velocities = [item[1] for item in self.history]
            pressures = [item[2] for item in self.history]
            if max(velocities) - min(velocities) >= 0.5:
                lag = best_pressure_lag(velocities, pressures)
                if lag and lag["correlation"] >= 0.55:
                    self.pa_lags.append(lag["lag_samples"])
                    self.last_pa_evaluation = now
            self.snapshot["pa_windows"] = len(self.pa_lags)

        current_pa = sample.get("pressure_advance")
        minimum_windows = int(self.config["min_pa_windows"])
        if not context.get("active"):
            self.snapshot["pa_confidence"] = "context_waiting"
        elif not context.get("pa_eligible"):
            self.snapshot["pa_confidence"] = "context_ignored"
        elif (_finite(current_pa) and len(self.pa_lags) >= minimum_windows):
            lag = _median(self.pa_lags)
            direction = 1 if lag >= 1 else -1 if lag <= -1 else 0
            self.snapshot["suggested_pa"] = _clamp(
                float(current_pa) + direction * self.config["pa_step"],
                self.config["pa_min"], self.config["pa_max"])
            self.snapshot["pa_confidence"] = (
                "ready" if direction else "stable")
        else:
            self.snapshot["pa_confidence"] = "learning"

        if self.previous_velocity >= 0.2 and velocity <= 0.02:
            self.pending_retract_at = now + 0.25
        if (self.pending_retract_at is not None
                and now >= self.pending_retract_at and quiet):
            self.retract_residuals.append(normalized)
            self.pending_retract_at = None
            self.last_retract_evaluation = now
        self.previous_velocity = velocity
        self.snapshot["retract_events"] = len(self.retract_residuals)

        minimum_events = int(self.config["min_retract_events"])
        if (_finite(current_retract_mm)
                and len(self.retract_residuals) >= minimum_events):
            residual = _median(self.retract_residuals)
            direction = 1 if residual > 0.15 else -1 if residual < -0.15 else 0
            self.snapshot["suggested_retract_mm"] = _clamp(
                float(current_retract_mm)
                + direction * self.config["retract_step_mm"],
                self.config["retract_min_mm"],
                self.config["retract_max_mm"])
            self.snapshot["retract_confidence"] = (
                "ready" if direction else "stable")
        else:
            self.snapshot["retract_confidence"] = "learning"
        self.snapshot["reason"] = "ok"
        return dict(self.snapshot)


class AdaptiveController:
    """Background control loop with transient arming and hard command limits."""

    def __init__(self, live_status_path, control_state_path,
                 moonraker_url="http://127.0.0.1:7125",
                 allow_printer_commands=False, poll_interval=0.1,
                 send_gcode=None):
        self.live_status_path = os.path.expanduser(live_status_path)
        self.control_state_path = os.path.expanduser(control_state_path)
        self.moonraker_url = moonraker_url.rstrip("/")
        self.allow_printer_commands = bool(allow_printer_commands)
        self.poll_interval = poll_interval
        self.config = dict(DEFAULT_CONFIG)
        self._load_config()
        if self.config["mode"] == "apply":
            self.config["mode"] = "dry_run"
        try:
            self.config = validated_config(DEFAULT_CONFIG, self.config)
        except ValueError:
            self.config = dict(DEFAULT_CONFIG)
        self.estimator = AdaptiveEstimator(self.config)
        self.context_timeline = ContextTimeline()
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.armed_until = 0.0
        self.seen_printing = False
        self.initial_pa = None
        self.initial_retract = None
        self.current_retract = None
        self.firmware_retraction_available = False
        # None means "has not happened yet". These must not be seeded with
        # 0.0: time.monotonic() is seconds since boot on Linux, so on a
        # freshly started machine 0.0 reads as a real, very recent timestamp
        # and the rate limiters below suppress the first genuine action.
        self.last_retraction_query_at = None
        self.last_command_at = None
        self.command_count = 0
        self.last_command = None
        self.last_error = None
        self.input_error = None
        self.last_sample = {
            "e_velocity": None,
            "volumetric_flow_mm3_s": None,
            "toolhead_velocity": None,
            "print_time": None,
        }
        self.pa_was_applied = False
        self.retract_was_applied = False
        self._send_gcode = send_gcode or self._moonraker_gcode

    def _load_config(self):
        try:
            with open(self.control_state_path, encoding="utf-8") as handle:
                payload = json.load(handle)
            for key in DEFAULT_CONFIG:
                if key in payload:
                    self.config[key] = payload[key]
        except (FileNotFoundError, OSError, ValueError):
            pass

    def _save_config(self):
        parent = os.path.dirname(self.control_state_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        temporary = self.control_state_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, self.control_state_path)

    def _moonraker_gcode(self, script):
        body = json.dumps({"script": script}).encode("utf-8")
        request = urllib.request.Request(
            self.moonraker_url + "/printer/gcode/script",
            data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=2.0) as response:
            json.load(response)

    def _refresh_firmware_retraction(self):
        now = time.monotonic()
        if (self.last_retraction_query_at is not None
                and now - self.last_retraction_query_at < 2.0):
            return
        self.last_retraction_query_at = now
        request = urllib.request.Request(
            self.moonraker_url
            + "/printer/objects/query?firmware_retraction",
            headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=1.5) as response:
                payload = json.load(response)
            retraction = (
                payload.get("result", {}).get("status", {})
                .get("firmware_retraction"))
            self.firmware_retraction_available = isinstance(
                retraction, dict) and bool(retraction)
            if self.firmware_retraction_available:
                value = retraction.get("retract_length")
                if _finite(value):
                    self.current_retract = float(value)
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            # A read failure only disables Auto-Retract evidence. It must never
            # disturb a print or the independent Adaptive-PA path.
            self.firmware_retraction_available = False

    def _read_live(self):
        with open(self.live_status_path, encoding="utf-8") as handle:
            return json.load(handle)

    def update_config(self, values):
        with self.lock:
            if not isinstance(values, dict):
                raise ValueError("control settings must be an object")
            if self.config["mode"] == "apply":
                requested_mode = values.get("mode")
                if requested_mode not in {"off", "dry_run"}:
                    raise ValueError(
                        "disarm before changing active control settings")
                self.disarm("user", restore=True)
            self.config = validated_config(self.config, values)
            self.estimator.update_config(self.config)
            self._save_config()
        return self.status()

    def arm(self, phrase):
        if phrase != ARM_PHRASE:
            raise ValueError("confirmation phrase does not match")
        if not self.allow_printer_commands:
            raise PermissionError("printer commands are server-side locked")
        with self.lock:
            if not (
                    self.config["adaptive_pa_enabled"]
                    or self.config["auto_retract_enabled"]):
                raise ValueError("enable Adaptive PA or Auto-Retract first")
            if (self.config["auto_retract_enabled"]
                    and not self.config["adaptive_pa_enabled"]
                    and not self.firmware_retraction_available):
                raise ValueError(
                    "Auto-Retract requires Klipper firmware_retraction")
            self.armed_until = time.monotonic() + 1800.0
            self.config["mode"] = "apply"
            self.last_error = None
        return self.status()

    def _restore_originals(self):
        restore_commands = []
        if self.pa_was_applied and _finite(self.initial_pa):
            restore_commands.append(
                "SET_PRESSURE_ADVANCE ADVANCE=%.6f" % self.initial_pa)
        if self.retract_was_applied and _finite(self.initial_retract):
            restore_commands.append(
                "SET_RETRACTION RETRACT_LENGTH=%.3f"
                % self.initial_retract)
        errors = []
        for command in restore_commands:
            try:
                self._send_gcode(command)
                self.last_command = command
                self.command_count += 1
                if command.startswith("SET_RETRACTION "):
                    self.current_retract = self.initial_retract
            except Exception as exc:
                errors.append(repr(exc))
        if errors:
            self.last_error = "restore_failed: " + "; ".join(errors)

    def disarm(self, reason="user", restore=True):
        with self.lock:
            if restore and self.allow_printer_commands:
                self._restore_originals()
            self.armed_until = 0.0
            if self.config["mode"] == "apply":
                self.config["mode"] = "dry_run"
            if not self.last_error:
                self.last_error = None if reason == "user" else reason
            self.seen_printing = False
            self.initial_pa = None
            self.initial_retract = None
            self.pa_was_applied = False
            self.retract_was_applied = False
        return self.status()

    def _bounded_suggestion(self, suggested, initial, maximum_delta):
        if not _finite(suggested) or not _finite(initial):
            return None
        return _clamp(
            float(suggested),
            float(initial) - maximum_delta,
            float(initial) + maximum_delta)

    def _maybe_apply(self, sample, estimate):
        now = time.monotonic()
        if self.config["mode"] != "apply":
            return
        if now >= self.armed_until:
            self.disarm("arming_expired", restore=True)
            return
        if sample.get("print_state") != "printing":
            if self.seen_printing:
                self.disarm("print_finished", restore=True)
            return
        self.seen_printing = True
        if estimate.get("reason") != "ok":
            return
        if (self.last_command_at is not None
                and now - self.last_command_at
                < self.config["min_update_interval_s"]):
            return
        command = None
        command_kind = None
        if (self.config["adaptive_pa_enabled"]
                and estimate.get("pa_context_eligible")):
            current = sample.get("pressure_advance")
            if self.initial_pa is None and _finite(current):
                self.initial_pa = float(current)
            proposed = self._bounded_suggestion(
                estimate.get("suggested_pa"), self.initial_pa,
                self.config["pa_max_total_delta"])
            if (_finite(current) and _finite(proposed)
                    and abs(proposed - float(current)) >= 0.5
                    * self.config["pa_step"]):
                command = "SET_PRESSURE_ADVANCE ADVANCE=%.6f" % proposed
                command_kind = "pa"
        if (command is None
                and self.config["auto_retract_enabled"]
                and self.firmware_retraction_available):
            if self.initial_retract is None and _finite(self.current_retract):
                self.initial_retract = float(self.current_retract)
            proposed = self._bounded_suggestion(
                estimate.get("suggested_retract_mm"), self.initial_retract,
                self.config["retract_max_total_delta_mm"])
            if (_finite(self.current_retract) and _finite(proposed)
                    and abs(proposed - self.current_retract) >= 0.5
                    * self.config["retract_step_mm"]):
                command = (
                    "SET_RETRACTION RETRACT_LENGTH=%.3f" % proposed)
                command_kind = "retract"
        if command is None:
            return
        try:
            self._send_gcode(command)
            self.last_command = command
            self.command_count += 1
            self.last_command_at = now
            if command_kind == "pa":
                self.pa_was_applied = True
            elif command_kind == "retract":
                self.retract_was_applied = True
                self.current_retract = proposed
        except Exception as exc:
            self.last_error = repr(exc)
            self.disarm("command_failed", restore=True)

    def step(self, live=None, current_retract_mm=None):
        try:
            if current_retract_mm is None:
                self._refresh_firmware_retraction()
            live = self._read_live() if live is None else live
            sample = live_sample(live)
            self.context_timeline.observe(
                (live.get("gcode_context") or {}).get("transitions"))
            sample["gcode_context"] = self.context_timeline.resolve(
                sample.get("print_time"))
            velocity = sample.get("e_velocity")
            diameter = self.config["filament_diameter_mm"]
            sample["volumetric_flow_mm3_s"] = (
                math.pi * (diameter / 2.0) ** 2 * max(0.0, float(velocity))
                if _finite(velocity) else None)
            self.last_sample = dict(sample)
            if current_retract_mm is not None:
                self.current_retract = current_retract_mm
                self.firmware_retraction_available = True
            estimate = self.estimator.observe(
                sample, current_retract_mm=self.current_retract)
            with self.lock:
                self._maybe_apply(sample, estimate)
            self.input_error = None
            return estimate
        except FileNotFoundError:
            # The live file does not exist between captures or during initial
            # startup. This is an idle/waiting state, not a sticky controller
            # fault and must never look like a failed printer command.
            self.input_error = None
            self.estimator.snapshot["reason"] = "waiting_for_live_data"
            return None
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            # Malformed or temporarily unreadable input is visible while it
            # persists, then clears automatically after the next valid read.
            self.input_error = repr(exc)
            return None

    def _run(self):
        while not self.stop_event.wait(self.poll_interval):
            self.step()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run, name="autopa-adaptive", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(2.0)

    def status(self):
        with self.lock:
            estimate = dict(self.estimator.snapshot)
            return {
                "mode": self.config["mode"],
                "allowPrinterCommands": self.allow_printer_commands,
                "armed": (
                    self.config["mode"] == "apply"
                    and time.monotonic() < self.armed_until),
                "armedSecondsRemaining": max(
                    0.0, self.armed_until - time.monotonic()),
                "adaptivePAEnabled":
                    bool(self.config["adaptive_pa_enabled"]),
                "autoRetractEnabled":
                    bool(self.config["auto_retract_enabled"]),
                "firmwareRetractionAvailable":
                    self.firmware_retraction_available,
                "config": dict(self.config),
                "pressure": estimate.get("pressure"),
                "suggestedPA": estimate.get("suggested_pa"),
                "suggestedRetractMm":
                    estimate.get("suggested_retract_mm"),
                "paConfidence": estimate.get("pa_confidence"),
                "retractConfidence":
                    estimate.get("retract_confidence"),
                "paWindows": estimate.get("pa_windows", 0),
                "retractEvents": estimate.get("retract_events", 0),
                "reason": estimate.get("reason"),
                "gcodeContext": estimate.get("gcode_context"),
                "paContextEligible":
                    bool(estimate.get("pa_context_eligible")),
                "extruderVelocityMmS":
                    self.last_sample.get("e_velocity"),
                "toolheadVelocityMmS":
                    self.last_sample.get("toolhead_velocity"),
                "volumetricFlowMm3S":
                    self.last_sample.get("volumetric_flow_mm3_s"),
                "contextPrintTime":
                    self.last_sample.get("print_time"),
                "commandCount": self.command_count,
                "lastCommand": self.last_command,
                "lastError": self.last_error or self.input_error,
                "printerAction": (
                    "bounded_runtime_adjustment"
                    if self.config["mode"] == "apply" else "none"),
            }


def main():
    parser = argparse.ArgumentParser(
        description="Run the bounded AutoPA validation controller")
    parser.add_argument(
        "--live-status",
        default=os.path.expanduser("~/printer_data/autopa/live.json"))
    parser.add_argument(
        "--control-state",
        default=os.path.expanduser(
            "~/.local/state/autopa/control.json"))
    parser.add_argument(
        "--moonraker-url", default="http://127.0.0.1:7125")
    parser.add_argument(
        "--allow-printer-commands", action="store_true")
    args = parser.parse_args()
    controller = AdaptiveController(
        args.live_status, args.control_state,
        moonraker_url=args.moonraker_url,
        allow_printer_commands=args.allow_printer_commands)
    controller.start()
    try:
        while True:
            print(json.dumps(
                controller.status(), sort_keys=True), flush=True)
            time.sleep(5.0)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
