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
from .apply_policy import apply_decision, validated_apply_bound
from .retract_sweep import MAX_RETRACT_MM, build_retract_sweep
from .sweep import decimal_range, validated_position


RUN_BOUNDS = {
    "r_start": (0.0, 5.0),
    "r_stop": (0.05, MAX_RETRACT_MM),
    "r_step": (0.01, 2.0),
    "cycles": (3, 30),
}
MAX_VALUES = 25
MAX_SCRIPT_LINES = 4000


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def _moonraker_post(url, payload, timeout=5.0):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class RetractSweepRunner:
    """Single-shot sweep runner; it never starts during an active print."""

    def __init__(self, moonraker_url="http://127.0.0.1:7125",
                 allow_printer_commands=False, send_script=None):
        self.moonraker_url = moonraker_url.rstrip("/")
        self.allow_printer_commands = bool(allow_printer_commands)
        self._send_script = send_script or self._moonraker_script
        self.last_run = None
        self.last_error = None
        self.last_apply = None

    def _moonraker_script(self, script):
        return _moonraker_post(
            self.moonraker_url + "/printer/gcode/script",
            {"script": script})

    def _printer_status(self):
        request = urllib.request.Request(
            self.moonraker_url
            + "/printer/objects/query?print_stats&firmware_retraction",
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.load(response)
        return payload.get("result", {}).get("status", {})

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
            "maxValues": MAX_VALUES,
            "lastRun": self.last_run,
            "lastError": self.last_error,
            "lastApply": self.last_apply,
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
        retraction = status.get("firmware_retraction") or {}
        restore_retract = retraction.get("retract_length")
        if not _finite(restore_retract):
            raise ValueError("Klipper firmware_retraction is not available")
        retract_speed = retraction.get("retract_speed")
        if not _finite(retract_speed) or retract_speed <= 0:
            retract_speed = 35.0

        values, retract_values = self._validated_values(payload)
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
            start_z=position["start_z"], prime_e=position["prime_e"])
        lines = gcode.splitlines()
        if len(lines) > MAX_SCRIPT_LINES:
            raise ValueError("generated sweep is unexpectedly large")

        self._send_script(gcode)
        self.last_run = {
            "startedAt": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "retractValues": retract_values,
            "cycles": values["cycles"],
            "restoreRetractMm": float(restore_retract),
            "startZMm": position["start_z"],
            "primeEMm": position["prime_e"],
            "estimatedDurationS": plan["estimated_sweep_duration_s"],
            "filamentLengthMm": plan["filament_length_mm"],
            "scriptLines": len(lines),
            "autoApply": auto_apply,
            "applyBoundMm": apply_bound,
        }
        self.last_error = None
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
            self.last_apply = {
                "applied": False,
                "reason": decision["reason"],
                "recommendedMm": decision["recommended"],
                "currentMm": decision["current"],
                "deviationMm": decision["deviation"],
                "boundMm": decision["bound"],
                "source": source,
                "at": applied_at,
                "printerAction": "none",
            }
            return self.status()
        self._send_script(
            "SET_RETRACTION RETRACT_LENGTH=%.3f" % decision["recommended"])
        self.last_apply = {
            "applied": True,
            "runtimeOnly": True,
            "previousMm": decision["current"],
            "appliedMm": decision["recommended"],
            "deviationMm": decision["deviation"],
            "boundMm": decision["bound"],
            "source": source,
            "at": applied_at,
            "printerAction": "set_retraction_runtime_only",
        }
        return self.status()

    def record_apply_skip(self, reason, source=None):
        self.last_apply = {
            "applied": False,
            "reason": str(reason),
            "source": source,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "printerAction": "none",
        }
        return self.status()

    def record_error(self, message):
        self.last_error = str(message)
        return self.status()
