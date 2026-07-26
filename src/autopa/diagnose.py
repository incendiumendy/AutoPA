"""Read-only live checks for the AutoPA Klipper endpoints."""
import argparse
import json
import os
import time

from .sync_recorder import KlippyConnection


def request(connection, method, params=None, timeout=3.0):
    request_id = connection.send(method, params)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for message in connection.receive():
            if message.get("id") == request_id:
                return message
    raise TimeoutError("Timed out waiting for %s" % method)


def diagnose(klippy_socket, add_marker=False, validate=False):
    connection = KlippyConnection(klippy_socket)
    connection.connect()
    try:
        clock = request(connection, "autopa/clock")
        initial = request(connection, "autopa/events", {"after": -1})
        result = {
            "clock_response": clock,
            "events_response": initial,
        }
        help_response = request(connection, "gcode/help")
        command_help = help_response.get("result", {})
        result["commands"] = {
            name: command_help.get(name)
            for name in ("AUTOPA_MARK", "AUTOPA_VALIDATE")
            if name in command_help
        }
        if add_marker:
            baseline = initial.get("result", {}).get("last_sequence", 0)
            marker = request(connection, "gcode/script", {
                "script":
                    "AUTOPA_MARK EVENT=diagnostic VALUE=endpoint_check"})
            events = request(
                connection, "autopa/events", {"after": baseline})
            result["marker_response"] = marker
            result["events_after_marker_response"] = events
        if validate:
            result["safety_validation"] = request(
                connection, "gcode/script", {
                    "script": "AUTOPA_VALIDATE X_TRAVEL=8 MIN_Z=10"})
        return result
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Check live AutoPA Klipper endpoints without movement")
    parser.add_argument(
        "--klippy-socket",
        default=os.path.expanduser("~/printer_data/comms/klippy.sock"))
    parser.add_argument("--add-marker", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        diagnose(args.klippy_socket, args.add_marker, args.validate),
        indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
