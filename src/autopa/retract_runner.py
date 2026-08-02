"""Bounded, explicitly confirmed retraction-sweep runner.

Builds the marked firmware-retraction sweep in memory and sends it to
Moonraker as one G-code script, so no .gcode file has to be stored in the
printer's gcode directory. Every run requires the server-side command flag,
the exact confirmation phrase, a non-printing printer and a working
[firmware_retraction] object. The generated script still contains
AUTOPA_VALIDATE and always restores the retraction length that was active
when the run started.
"""
import math
import time
import urllib.error
import urllib.request
import json

from .adaptive import ARM_PHRASE
from .apply_policy import (
    apply_decision, summarize_analysis, validated_apply_bound)
from .retract_sweep import (
    MAX_RETRACT_MM, MAX_RETRACT_SPEED_MM_S, MIN_RETRACT_SPEED_MM_S,
    build_retract_sweep)
from .sweep import decimal_range, validated_position


RUN_BOUNDS = {
    "r_start": (0.0, 5.0),
    "r_stop": (0.05, MAX_RETRACT_MM),
    "r_step": (0.01, 2.0),
    "cycles": (3, 30),
}
# A speed sweep holds the length at the printer's configured value and varies
# how fast the filament is pulled. Material viscosity decides how quickly the
# melt can follow, so this is a separate stage rather than a second dimension
# of the length sweep.
SPEED_BOUNDS = {
    "v_start": (MIN_RETRACT_SPEED_MM_S, MAX_RETRACT_SPEED_MM_S),
    "v_stop": (MIN_RETRACT_SPEED_MM_S, MAX_RETRACT_SPEED_MM_S),
    "v_step": (1.0, 40.0),
    "cycles": (3, 30),
}
MAX_VALUES = 25
MAX_SCRIPT_LINES = 4000


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def _current_z(status):
    """Return the live toolhead Z position when Klipper reports it."""
    position = (status.get("toolhead") or {}).get("position")
    if (isinstance(position, (list, tuple)) and len(position) >= 3
            and _finite(position[2])):
        return float(position[2])
    return None


def _require_homed(status):
    """Refuse the sweep when Klipper reports unhomed axes."""
    homed = (status.get("toolhead") or {}).get("homed_axes")
    if homed is None:
        return
    if not all(axis in str(homed).lower() for axis in "xyz"):
        raise ValueError(
            "Der Drucker ist nicht gehomt. Fahre zuerst G28 — der Sweep "
            "bewegt die Achsen und braucht bekannte Positionen. "
            "(gehomte Achsen: %s)" % (homed or "keine"))


def _moonraker_post(url, payload, timeout=5.0):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Klipper rejects a script through AUTOPA_VALIDATE with a plain
        # message - a cold nozzle, unhomed axes, too little Z clearance.
        # Letting the HTTPError escape killed the request thread and the
        # browser saw an empty reply instead of the reason.
        raise ValueError(_moonraker_error(exc)) from None


def _moonraker_error(exc):
    detail = ""
    try:
        payload = json.loads(exc.read().decode("utf-8", "replace"))
        detail = (
            payload.get("error", {}).get("message")
            if isinstance(payload.get("error"), dict)
            else payload.get("error") or payload.get("message") or "")
    except Exception:
        detail = ""
    detail = str(detail or exc.reason or "").strip()
    if "min_extrude_temp" in detail or "hot extruder" in detail:
        return ("Die Düse ist zu kalt. Heize das eingelegte Filament auf "
                "Drucktemperatur, bevor du eine Stufe startest — der Sweep "
                "extrudiert und Klipper lehnt kaltes Extrudieren ab.")
    return "Klipper hat den Sweep abgelehnt: %s" % (detail or "unbekannt")


class RetractSweepRunner:
    """Single-shot sweep runner; it never starts during an active print."""

    def __init__(self, moonraker_url="http://127.0.0.1:7125",
                 allow_printer_commands=False, send_script=None,
                 script_timeout=5.0):
        self.moonraker_url = moonraker_url.rstrip("/")
        self.allow_printer_commands = bool(allow_printer_commands)
        self._send_script = send_script or self._moonraker_script
        # Moonraker answers a gcode/script request only after Klipper has
        # processed the whole script, so the timeout is raised to the
        # estimated sweep duration before every send.
        self._script_timeout = float(script_timeout)
        self.last_run = None
        self.last_error = None
        self.last_apply = None
        self.last_analysis = None
        self.running = None
        self.last_analysis_by_mode = {"length": None, "speed": None}
        # Stage 2 and stage 3 share this runner, so one slot meant the later
        # stage erased the earlier one's result and its card went blank.
        self.last_apply_by_mode = {"length": None, "speed": None}
        self.last_run_by_mode = {"length": None, "speed": None}
        self.last_save = None
        self.active_mode = "length"

    def _moonraker_script(self, script):
        return _moonraker_post(
            self.moonraker_url + "/printer/gcode/script",
            {"script": script}, timeout=self._script_timeout)

    def _printer_status(self):
        request = urllib.request.Request(
            self.moonraker_url
            + "/printer/objects/query?print_stats&firmware_retraction"
            + "&toolhead",
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.load(response)
        return payload.get("result", {}).get("status", {})

    @staticmethod
    def _validated_speeds(payload):
        values = {}
        for key, limits in SPEED_BOUNDS.items():
            raw = payload.get(key)
            if isinstance(raw, bool) or not _finite(raw):
                raise ValueError("%s must be a finite number" % key)
            value = float(raw)
            if not limits[0] <= value <= limits[1]:
                raise ValueError("%s is outside the safe range" % key)
            values[key] = value
        values["cycles"] = int(values["cycles"])
        if values["v_start"] >= values["v_stop"]:
            raise ValueError("v_start must be smaller than v_stop")
        speed_values = decimal_range(
            values["v_start"], values["v_stop"], values["v_step"])
        if len(speed_values) > MAX_VALUES:
            raise ValueError(
                "sweep would exceed %d retract speeds" % MAX_VALUES)
        return values, speed_values

    @staticmethod
    def _validated_values(payload):
        values = {}
        for key, limits in RUN_BOUNDS.items():
            raw = payload.get(key)
            if isinstance(raw, bool) or not _finite(raw):
                raise ValueError("%s must be a finite number" % key)
            value = float(raw)
            if not limits[0] <= value <= limits[1]:
                raise ValueError("%s is outside the safe range" % key)
            values[key] = value
        values["cycles"] = int(values["cycles"])
        if values["r_start"] >= values["r_stop"]:
            raise ValueError("r_start must be smaller than r_stop")
        retract_values = decimal_range(
            values["r_start"], values["r_stop"], values["r_step"])
        if len(retract_values) > MAX_VALUES:
            raise ValueError(
                "sweep would exceed %d retract values" % MAX_VALUES)
        return values, retract_values

    def status(self):
        return {
            "allowPrinterCommands": self.allow_printer_commands,
            "confirmationPhraseRequired": True,
            "bounds": {key: list(limits)
                       for key, limits in RUN_BOUNDS.items()},
            "speedBounds": {key: list(limits)
                            for key, limits in SPEED_BOUNDS.items()},
            "maxValues": MAX_VALUES,
            "lastRun": self.last_run,
            "lastError": self.last_error,
            "lastApply": self.last_apply,
            "lastAnalysis": self.last_analysis,
            "running": self.run_progress(),
            "lastAnalysisByMode": self.last_analysis_by_mode,
            "lastApplyByMode": self.last_apply_by_mode,
            "lastRunByMode": self.last_run_by_mode,
            "lastSave": self.last_save,
            "printerAction": "none",
        }

    def run(self, payload, printer_status=None):
        if not isinstance(payload, dict):
            raise ValueError("sweep settings must be an object")
        if str(payload.get("phrase", "")) != ARM_PHRASE:
            raise ValueError("confirmation phrase does not match")
        if not self.allow_printer_commands:
            raise PermissionError("printer commands are server-side locked")

        status = (
            printer_status if printer_status is not None
            else self._printer_status())
        print_state = (
            (status.get("print_stats") or {}).get("state"))
        if print_state != "standby":
            raise ValueError(
                "printer must be in standby, not %s" % (print_state or "?"))
        _require_homed(status)
        retraction = status.get("firmware_retraction") or {}
        restore_retract = retraction.get("retract_length")
        if not _finite(restore_retract):
            raise ValueError("Klipper firmware_retraction is not available")
        retract_speed = retraction.get("retract_speed")
        if not _finite(retract_speed) or retract_speed <= 0:
            retract_speed = 35.0

        speed_sweep = str(payload.get("mode", "length")) == "speed"
        if speed_sweep:
            values, speed_values = self._validated_speeds(payload)
            retract_values = [float(restore_retract)]
        else:
            values, retract_values = self._validated_values(payload)
            speed_values = None
        auto_apply = bool(payload.get("auto_apply", True))
        apply_bound = validated_apply_bound(
            payload.get("apply_bound"), "retract")
        position = validated_position(
            payload.get("start_x"), payload.get("start_y"),
            payload.get("start_z"), payload.get("prime_e", 0.0))
        gcode, plan = build_retract_sweep(
            retract_values, values["cycles"],
            retract_speed=float(retract_speed),
            restore_retract=float(restore_retract),
            start_x=position["start_x"], start_y=position["start_y"],
            start_z=position["start_z"], prime_e=position["prime_e"],
            current_z=_current_z(status),
            speed_values=speed_values,
            restore_retract_speed=(
                float(retract_speed) if speed_sweep else None))
        lines = gcode.splitlines()
        if len(lines) > MAX_SCRIPT_LINES:
            raise ValueError("generated sweep is unexpectedly large")

        self._script_timeout = min(
            max(plan["estimated_sweep_duration_s"] + 120.0, 60.0), 900.0)
        self._begin_run(plan["estimated_sweep_duration_s"])
        try:
            self._send_script(gcode)
        finally:
            self._end_run()
        self.last_run = {
            "startedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "mode": "speed" if speed_sweep else "length",
            "retractValues": retract_values,
            "speedValues": speed_values,
            "heldRetractMm": float(restore_retract) if speed_sweep else None,
            "restoreRetractSpeedMmS": (
                float(retract_speed) if speed_sweep else None),
            "cycles": values["cycles"],
            "restoreRetractMm": float(restore_retract),
            "startZMm": position["start_z"],
            "primeEMm": position["prime_e"],
            "zLift": bool(plan.get("z_lift")),
            "estimatedDurationS": plan["estimated_sweep_duration_s"],
            "filamentLengthMm": plan["filament_length_mm"],
            "scriptLines": len(lines),
            "autoApply": auto_apply,
            "applyBoundMm": apply_bound,
        }
        self.last_error = None
        self.active_mode = "speed" if speed_sweep else "length"
        self.last_run_by_mode[self.active_mode] = self.last_run
        # A fresh run invalidates whatever this stage reported before.
        self.last_apply_by_mode[self.active_mode] = None
        self.last_analysis_by_mode[self.active_mode] = None
        return self.status()

    def _record(self, entry):
        """Store a result as the latest and under the stage that produced it."""
        self.last_apply = entry
        self.last_apply_by_mode[self.active_mode] = entry
        return self.status()

    def apply_recommendation(self, recommended, source=None):
        """Apply a bounded recommendation at runtime; never persisted."""
        if not self.allow_printer_commands:
            raise PermissionError("printer commands are server-side locked")
        bound = validated_apply_bound(
            (self.last_run or {}).get("applyBoundMm"), "retract")
        current = (
            (self._printer_status().get("firmware_retraction") or {})
            .get("retract_length"))
        decision = apply_decision(recommended, current, bound)
        applied_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not decision["eligible"]:
            self._record({
                "applied": False,
                "reason": decision["reason"],
                "recommendedMm": decision["recommended"],
                "currentMm": decision["current"],
                "deviationMm": decision["deviation"],
                "boundMm": decision["bound"],
                "source": source,
                "at": applied_at,
                "printerAction": "none",
            })
            return self.status()
        self._send_script(
            "SET_RETRACTION RETRACT_LENGTH=%.3f" % decision["recommended"])
        self._record({
            "applied": True,
            "runtimeOnly": True,
            "previousMm": decision["current"],
            "appliedMm": decision["recommended"],
            "deviationMm": decision["deviation"],
            "boundMm": decision["bound"],
            "source": source,
            "at": applied_at,
            "printerAction": "set_retraction_runtime_only",
        })
        return self.status()

    def save_config(self, payload, printer_status=None):
        """Persist the current runtime values through Klipper's SAVE_CONFIG.

        This is the one place AutoPA writes to printer.cfg, and it is opt-in
        per call. SAVE_CONFIG rewrites the config file and restarts Klipper,
        so it is gated on standby, the confirmation phrase and the same
        server-side command lock as every other printer action.
        """
        if not isinstance(payload, dict):
            raise ValueError("save settings must be an object")
        if str(payload.get("phrase", "")) != ARM_PHRASE:
            raise ValueError("confirmation phrase does not match")
        if not self.allow_printer_commands:
            raise PermissionError("printer commands are server-side locked")
        status = (
            printer_status if printer_status is not None
            else self._printer_status())
        print_state = (status.get("print_stats") or {}).get("state")
        if print_state != "standby":
            # SAVE_CONFIG restarts the firmware. Doing that during a print
            # would abort it.
            raise ValueError(
                "printer must be in standby, not %s" % (print_state or "?"))
        self._send_script("SAVE_CONFIG")
        self.last_save = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "restarted": True,
            "printerAction": "save_config_and_restart",
        }
        return self.status()

    def record_advisory(self, recommendation, source=None):
        """Record a result this runner may not apply on its own.

        The retraction-speed sweep ranks candidates exactly like the length
        sweep, but its winner is a speed. Applying it would need a bounded
        speed policy that does not exist, and the ALPS cannot detect a
        skipping extruder, so the value is reported and left to the operator.
        """
        self._record({
            "applied": False,
            "advisory": True,
            "reason": "manual_apply_required",
            "sweptVariable": recommendation.get("swept_variable"),
            "recommendedSpeedMmS": recommendation.get("retract_speed_mm_s"),
            "cost": recommendation.get("cost"),
            "costGapToSecondBest": recommendation.get(
                "cost_gap_to_second_best"),
            "source": source,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "printerAction": "none",
        })
        return self.status()

    def _begin_run(self, estimated_s):
        """Mark the sweep as running before the script is sent.

        Moonraker only answers once Klipper has executed the whole script, so
        without this the server has no signal at all while the printer is
        moving: last_run was written after the fact and the card still showed
        its start button.
        """
        self.running = {
            "active": True,
            "startedMonotonic": time.monotonic(),
            "estimatedDurationS": float(estimated_s),
        }

    def _end_run(self):
        self.running = None

    def run_progress(self):
        """How far the running sweep has got, for the stage progress bar."""
        if not self.running:
            return {"active": False, "percent": 0, "secondsRemaining": 0}
        total = max(1.0, self.running["estimatedDurationS"])
        elapsed = time.monotonic() - self.running["startedMonotonic"]
        # Capped just below 100 so the bar never claims to be finished while
        # the printer is still moving.
        percent = int(min(99.0, max(0.0, elapsed / total * 100.0)))
        return {
            "active": True,
            "percent": percent,
            "secondsRemaining": int(max(0.0, total - elapsed)),
        }

    def record_analysis(self, result):
        """Keep the per-candidate cost curve so the card can plot it."""
        self.last_analysis = summarize_analysis(result)
        # Stage 2 and stage 3 share this runner, so the curve is filed under
        # the stage that measured it.
        self.last_analysis_by_mode[self.active_mode] = self.last_analysis
        return self.last_analysis

    def record_apply_skip(self, reason, source=None):
        self._record({
            "applied": False,
            "reason": str(reason),
            "source": source,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "printerAction": "none",
        })
        return self.status()

    def record_error(self, message):
        self.last_error = str(message)
        return self.status()
