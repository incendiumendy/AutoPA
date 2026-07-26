# Clock synchronization and safe sweep markers for the external AutoPA recorder
#
# Copyright (C) 2026 AutoPA contributors
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging


class AutoPAClock:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.mcu = None
        self.sequence = 0
        self.events = []
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        webhooks = self.printer.lookup_object("webhooks")
        webhooks.register_endpoint("autopa/clock", self._handle_clock)
        webhooks.register_endpoint("autopa/events", self._handle_events)
        gcode = self.printer.lookup_object("gcode")
        gcode.register_command(
            "AUTOPA_MARK", self.cmd_AUTOPA_MARK,
            desc="Add an exact print-time marker for AutoPA")
        gcode.register_command(
            "AUTOPA_VALIDATE", self.cmd_AUTOPA_VALIDATE,
            desc="Check that an AutoPA sweep can run safely")

    def _handle_ready(self):
        self.mcu = self.printer.lookup_object("mcu")

    def _handle_clock(self, web_request):
        if self.mcu is None:
            raise self.printer.command_error("AutoPA clock is not ready")
        eventtime = self.reactor.monotonic()
        web_request.send({
            "host_monotonic": eventtime,
            "print_time": self.mcu.estimated_print_time(eventtime),
        })

    def _handle_events(self, web_request):
        after = web_request.get_int("after", -1)
        if after < 0:
            events = []
        else:
            events = [
                event for event in self.events
                if event["sequence"] > after
            ]
        web_request.send({
            "events": events,
            "last_sequence": self.sequence,
        })

    def cmd_AUTOPA_MARK(self, gcmd):
        # Markers are deliberately fail-open: malformed or failed telemetry
        # must never interrupt a normal print.
        try:
            event = gcmd.get("EVENT", "").strip()
            value = gcmd.get("VALUE", "")
            event = "_".join(event.split())
            if not event:
                gcmd.respond_info(
                    "AutoPA marker skipped: EVENT is empty", log=False)
                return
            toolhead = self.printer.lookup_object("toolhead")
            self.sequence += 1
            self.events.append({
                "sequence": self.sequence,
                "print_time": toolhead.get_last_move_time(),
                "host_monotonic": self.reactor.monotonic(),
                "event": event,
                "value": value,
            })
            # Retain enough markers for several sweeps without unbounded growth.
            if len(self.events) > 4096:
                self.events = self.events[-2048:]
        except Exception:
            logging.exception("AutoPA marker skipped after internal error")
            gcmd.respond_info(
                "AutoPA marker skipped after internal error", log=False)

    def cmd_AUTOPA_VALIDATE(self, gcmd):
        x_travel = gcmd.get_float("X_TRAVEL", 0., minval=0.)
        min_z = gcmd.get_float("MIN_Z", 10., minval=0.)
        target_temp = gcmd.get_float(
            "TARGET_TEMP", None, minval=0., maxval=500.)
        temp_tolerance = gcmd.get_float(
            "TEMP_TOLERANCE", 2., above=0., maxval=20.)
        eventtime = self.reactor.monotonic()
        toolhead = self.printer.lookup_object("toolhead")
        status = toolhead.get_status(eventtime)
        homed_axes = status.get("homed_axes", "")
        if "x" not in homed_axes or "y" not in homed_axes or "z" not in homed_axes:
            raise gcmd.error("AutoPA requires homed X, Y and Z axes")
        position = status["position"]
        axis_maximum = status["axis_maximum"]
        if position.z < min_z:
            raise gcmd.error(
                "AutoPA requires Z >= %.3fmm (current %.3fmm)"
                % (min_z, position.z))
        if position.x + x_travel > axis_maximum.x:
            raise gcmd.error(
                "AutoPA X travel exceeds axis maximum (%.3f + %.3f > %.3f)"
                % (position.x, x_travel, axis_maximum.x))
        extruder = toolhead.get_extruder()
        heater = extruder.get_heater()
        if not heater.can_extrude:
            raise gcmd.error(
                "AutoPA requires a hot extruder above min_extrude_temp")
        if target_temp is not None:
            heater_status = heater.get_status(eventtime)
            measured_temp = heater_status["temperature"]
            configured_target = heater_status["target"]
            if abs(measured_temp - target_temp) > temp_tolerance:
                raise gcmd.error(
                    "AutoPA requires nozzle %.1fC +/- %.1fC "
                    "(current %.1fC)"
                    % (target_temp, temp_tolerance, measured_temp))
            if abs(configured_target - target_temp) > temp_tolerance:
                raise gcmd.error(
                    "AutoPA heater target %.1fC does not match required %.1fC"
                    % (configured_target, target_temp))
        gcmd.respond_info(
            "AutoPA safety check passed at X%.3f Y%.3f Z%.3f"
            % (position.x, position.y, position.z))


def load_config(config):
    return AutoPAClock(config)
