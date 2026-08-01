import pathlib
import tempfile
import unittest

from autopa.chamber_filter import (
    ChamberFilterController, validated_profiles)


def printer_status(state="standby", filename=""):
    return {
        "print_stats": {
            "state": state,
            "filename": filename,
        },
        "configfile": {
            "settings": {
                "fan_generic chamber_filter": {
                    "pin": "multi_pin:chamber_filter_pins",
                },
                "fan": {"pin": "part_fan"},
            },
        },
    }


def filter_profile(tag="[FILTER]", post_run=10):
    return {
        "id": "abs",
        "name": "ABS",
        "filter_enabled": True,
        "filter_tag": tag,
        "filter_fan": "chamber_filter",
        "filter_speed_percent": 80,
        "filter_post_run_minutes": post_run,
    }


class ChamberFilterValidationTests(unittest.TestCase):
    def test_enabled_profile_requires_real_fan_generic(self):
        with self.assertRaisesRegex(ValueError, "unknown fan_generic"):
            validated_profiles(
                [{**filter_profile(), "filter_fan": "missing"}],
                ["chamber_filter"])

    def test_speed_and_post_run_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "10 and 100"):
            validated_profiles(
                [{**filter_profile(), "filter_speed_percent": 5}],
                ["chamber_filter"])
        with self.assertRaisesRegex(ValueError, "0 and 120"):
            validated_profiles(
                [{**filter_profile(), "filter_post_run_minutes": 121}],
                ["chamber_filter"])

    def test_enabled_tags_must_be_unique(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            validated_profiles(
                [filter_profile("[ABS]"), {
                    **filter_profile("[abs]"),
                    "id": "abs-2",
                }],
                ["chamber_filter"])


class ChamberFilterControllerTests(unittest.TestCase):
    def make_controller(self, directory, allowed=True, now=None, sent=None):
        now = now or {"value": 100.0}
        sent = sent if sent is not None else []
        controller = ChamberFilterController(
            str(pathlib.Path(directory, "filter.json")),
            allow_commands=allowed,
            send_gcode=sent.append,
            status_provider=lambda: printer_status(),
            wall_time=lambda: now["value"])
        controller.update_profiles([filter_profile()])
        return controller, now, sent

    def test_matching_filename_activates_and_stops_after_post_run(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, now, sent = self.make_controller(directory)
            status = controller.step(
                printer_status("printing", "part_[FILTER]_abs.gcode"))
            self.assertEqual("active", status["state"])
            self.assertEqual(
                "SET_FAN_SPEED FAN=chamber_filter SPEED=0.800", sent[0])
            self.assertEqual("chamber_filter_only", status["printerAction"])

            controller.step(
                printer_status("paused", "part_[FILTER]_abs.gcode"))
            self.assertEqual(1, len(sent))

            status = controller.step(printer_status("complete", ""))
            self.assertEqual("post_run", status["state"])
            self.assertAlmostEqual(600.0, status["postRunSecondsRemaining"])
            self.assertEqual(1, len(sent))

            now["value"] = 701.0
            status = controller.step(printer_status("standby", ""))
            self.assertEqual("idle", status["state"])
            self.assertEqual(
                "SET_FAN_SPEED FAN=chamber_filter SPEED=0.000", sent[1])
            self.assertEqual("none", status["printerAction"])

    def test_nonmatching_filename_never_sends_command(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, sent = self.make_controller(directory)
            status = controller.step(
                printer_status("printing", "plain_pla_part.gcode"))
            self.assertEqual("idle", status["state"])
            self.assertEqual([], sent)

    def test_server_lock_reports_match_without_command(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, sent = self.make_controller(
                directory, allowed=False)
            status = controller.step(
                printer_status("printing", "part_[filter].gcode"))
            self.assertEqual("matched_locked", status["state"])
            self.assertFalse(status["allowCommands"])
            self.assertEqual([], sent)

    def test_monitor_failure_keeps_an_active_filter_running(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, _, sent = self.make_controller(directory)
            controller.step(
                printer_status("printing", "part_[FILTER].gcode"))

            def unavailable():
                raise OSError("Moonraker unavailable")

            controller._status_provider = unavailable
            status = controller.step()
            self.assertEqual("monitor_warning", status["state"])
            self.assertEqual("chamber_filter", status["activeFan"])
            self.assertEqual(1, len(sent))

    def test_runtime_state_recovers_into_post_run_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, now, sent = self.make_controller(directory)
            controller.step(
                printer_status("printing", "part_[FILTER].gcode"))
            recovered = ChamberFilterController(
                str(pathlib.Path(directory, "filter.json")),
                allow_commands=True,
                send_gcode=sent.append,
                status_provider=lambda: printer_status("standby", ""),
                wall_time=lambda: now["value"])
            status = recovered.step()
            self.assertEqual("post_run", status["state"])
            self.assertEqual("chamber_filter", status["activeFan"])
            self.assertEqual(1, len(sent))


if __name__ == "__main__":
    unittest.main()
