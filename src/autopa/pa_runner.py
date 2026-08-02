"""Bounded, explicitly confirmed pressure-advance sweep runner.

Builds the marked AutoPA Klipper sweep in memory and sends it to Moonraker
as one G-code script, so no .gcode file has to be stored in the printer's
gcode directory. Every run requires the server-side command flag, the exact
confirmation phrase, a non-printing printer and a readable current pressure
advance value. The generated script still contains AUTOPA_VALIDATE and
always restores the pressure advance that was active when the run started.
"""
import time

from .adaptive import ARM_PHRASE
from .apply_policy import (
    apply_decision, summarize_analysis, validated_apply_bound)
from .retract_runner import MAX_SCRIPT_LINES, MAX_VALUES, _current_z, \
    _finite, _moonraker_post, _require_homed
from .sweep import build_sweep, decimal_range, validated_position


RUN_BOUNDS = {
    "k_start": (0.0, 0.2),
    "k_stop": (0.0, 0.2),
    "k_step": (0.001, 0.1),
    "cycles": (3, 30),
}


class PaSweepRunner:
    """Single-shot PA sweep runner; it never starts during an active print."""

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

    def _moonraker_script(self, script):
        return _moonraker_post(
            self.moonraker_url + "/printer/gcode/script",
            {"script": script}, timeout=self._script_timeout)

    def _printer_status(self):
        import json
        import urllib.request
        request = urllib.request.Request(
            self.moonraker_url
            + "/printer/objects/query?print_stats&extruder&toolhead",
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
        if values["k_start"] >= values["k_stop"]:
            raise ValueError("k_start must be smaller than k_stop")
        k_values = decimal_range(
            values["k_start"], values["k_stop"], values["k_step"])
        if len(k_values) > MAX_VALUES:
            raise ValueError(
                "sweep would exceed %d pressure advance values" % MAX_VALUES)
        return values, k_values

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
            "lastAnalysis": self.last_analysis,
            "running": self.run_progress(),
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
        extruder = status.get("extruder") or {}
        restore_advance = extruder.get("pressure_advance")
        if not _finite(restore_advance) or not 0.0 <= restore_advance <= 0.2:
            raise ValueError("Klipper pressure_advance is not available")

        values, k_values = self._validated_values(payload)
        auto_apply = bool(payload.get("auto_apply", True))
        # Capture and analysis are worth doing even when the
        # result may not be applied automatically.
        analyze = bool(payload.get("analyze", auto_apply))
        apply_bound = validated_apply_bound(
            payload.get("apply_bound"), "pa")
        position = validated_position(
            payload.get("start_x"), payload.get("start_y"),
            payload.get("start_z"), payload.get("prime_e", 0.0))
        gcode, plan = build_sweep(
            k_values, values["cycles"],
            restore_advance=float(restore_advance),
            start_x=position["start_x"], start_y=position["start_y"],
            start_z=position["start_z"], prime_e=position["prime_e"],
            current_z=_current_z(status))
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
            "kValues": k_values,
            "cycles": values["cycles"],
            "restoreAdvance": float(restore_advance),
            "startZMm": position["start_z"],
            "primeEMm": position["prime_e"],
            "zLift": bool(plan.get("z_lift")),
            "estimatedDurationS": plan["estimated_sweep_duration_s"],
            "filamentLengthMm": plan["filament_length_mm"],
            "scriptLines": len(lines),
            "autoApply": auto_apply,
            "analyze": analyze,
            "applyBound": apply_bound,
        }
        self.last_error = None
        return self.status()

    def apply_recommendation(self, recommended, source=None):
        """Apply a bounded recommendation at runtime; never persisted."""
        if not self.allow_printer_commands:
            raise PermissionError("printer commands are server-side locked")
        bound = validated_apply_bound(
            (self.last_run or {}).get("applyBound"), "pa")
        current = (
            (self._printer_status().get("extruder") or {})
            .get("pressure_advance"))
        decision = apply_decision(recommended, current, bound)
        applied_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not decision["eligible"]:
            self.last_apply = {
                "applied": False,
                "reason": decision["reason"],
                "recommended": decision["recommended"],
                "current": decision["current"],
                "deviation": decision["deviation"],
                "bound": decision["bound"],
                "source": source,
                "at": applied_at,
                "printerAction": "none",
            }
            return self.status()
        self._send_script(
            "SET_PRESSURE_ADVANCE ADVANCE=%.6f" % decision["recommended"])
        self.last_apply = {
            "applied": True,
            "runtimeOnly": True,
            "previous": decision["current"],
            "appliedValue": decision["recommended"],
            "deviation": decision["deviation"],
            "bound": decision["bound"],
            "source": source,
            "at": applied_at,
            "printerAction": "set_pressure_advance_runtime_only",
        }
        return self.status()

    def record_advisory(self, recommendation, source=None):
        """Record a result this runner may not apply on its own.

        A PA sweep always reports pressure_advance, so the shared pipeline
        should never route here. It exists so a recommendation shaped
        unexpectedly degrades into an advisory note instead of an
        AttributeError inside the post-sweep thread.
        """
        self.last_apply = {
            "applied": False,
            "advisory": True,
            "reason": "manual_apply_required",
            "sweptVariable": recommendation.get("swept_variable"),
            "cost": recommendation.get("cost"),
            "source": source,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "printerAction": "none",
        }
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
        return self.last_analysis

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
