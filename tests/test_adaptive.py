import pathlib
import sys
import tempfile
import time
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))
from autopa.adaptive import (
    ARM_PHRASE, DEFAULT_CONFIG, AdaptiveController, AdaptiveEstimator,
    best_pressure_lag, extruder_velocity_from_live,
    toolhead_velocity_from_live, validated_config)
from autopa.gcode_context import encode_context_marker


class AdaptiveMathTests(unittest.TestCase):
    def test_best_pressure_lag_detects_delayed_pressure(self):
        velocity = [0, 0, 1, 1, 0, 0, 2, 2, 0, 0, 1, 1, 0, 0]
        pressure = [0, 0] + velocity[:-2]
        result = best_pressure_lag(velocity, pressure, max_lag_samples=3)
        self.assertEqual(2, result["lag_samples"])
        self.assertGreater(result["correlation"], 0.99)

    def test_live_motion_segment_yields_signed_velocity(self):
        live = {
            "clock": {"host_monotonic": 10.0, "print_time": 100.0},
            "extruder_motion": {"segments": [{
                "print_time": 99.5,
                "duration_s": 1.0,
                "start_velocity_mm_s": 2.0,
                "acceleration_mm_s2": 1.0,
                "direction": -1.0,
                "pressure_advance_active": True,
            }]},
        }
        velocity, print_time, pa_active = extruder_velocity_from_live(
            live, now_monotonic_ns=10_000_000_000)
        self.assertAlmostEqual(-2.5, velocity)
        self.assertAlmostEqual(100.0, print_time)
        self.assertTrue(pa_active)

    def test_toolhead_motion_segment_yields_executed_speed(self):
        live = {"toolhead_motion": {"segments": [{
            "print_time": 99.5,
            "duration_s": 1.0,
            "start_velocity_mm_s": 40.0,
            "acceleration_mm_s2": 20.0,
        }]}}
        self.assertAlmostEqual(
            50.0, toolhead_velocity_from_live(live, 100.0))

    def test_estimator_learns_baseline_and_pressure(self):
        estimator = AdaptiveEstimator({
            "min_force_rate_hz": 1000.0,
            "max_acceleration_mm_s2": 50000.0,
        })
        now = 1.0
        for _ in range(30):
            estimator.observe({
                "host_monotonic": now,
                "force": 1000.0,
                "force_age_s": 0.01,
                "force_rate_hz": 2500.0,
                "acceleration": 0.0,
                "acceleration_errors": 0,
                "acceleration_overflows": 0,
                "e_velocity": 0.0,
                "print_state": "printing",
                "temperature": 210.0,
                "target": 210.0,
                "pressure_advance": 0.03,
            })
            now += 0.1
        result = estimator.observe({
            "host_monotonic": now,
            "force": 1300.0,
            "force_age_s": 0.01,
            "force_rate_hz": 2500.0,
            "acceleration": 100.0,
            "acceleration_errors": 0,
            "acceleration_overflows": 0,
            "e_velocity": 2.0,
            "print_state": "printing",
            "temperature": 210.0,
            "target": 210.0,
            "pressure_advance": 0.03,
        })
        self.assertEqual("ok", result["reason"])
        self.assertAlmostEqual(1000.0, result["pressure"]["baseline"])
        self.assertAlmostEqual(300.0, result["pressure"]["delta"])
        self.assertAlmostEqual(1.0, result["pressure"]["normalized"])


class AdaptiveControllerTests(unittest.TestCase):
    def test_missing_live_file_is_waiting_not_sticky_error(self):
        with tempfile.TemporaryDirectory() as directory:
            live = pathlib.Path(directory, "live.json")
            controller = AdaptiveController(
                str(live), str(pathlib.Path(directory, "control.json")))

            self.assertIsNone(controller.step())
            status = controller.status()
            self.assertEqual("waiting_for_live_data", status["reason"])
            self.assertIsNone(status["lastError"])

            live.write_text("{}", encoding="utf-8")
            controller.step()
            status = controller.status()
            self.assertEqual("force_missing", status["reason"])
            self.assertIsNone(status["lastError"])

    def test_transient_live_parse_error_clears_after_valid_read(self):
        with tempfile.TemporaryDirectory() as directory:
            live = pathlib.Path(directory, "live.json")
            live.write_text("{", encoding="utf-8")
            controller = AdaptiveController(
                str(live), str(pathlib.Path(directory, "control.json")))

            self.assertIsNone(controller.step())
            self.assertIn("JSONDecodeError", controller.status()["lastError"])

            live.write_text("{}", encoding="utf-8")
            controller.step()
            self.assertIsNone(controller.status()["lastError"])

    def test_apply_requires_server_unlock_and_exact_phrase(self):
        with tempfile.TemporaryDirectory() as directory:
            state = str(pathlib.Path(directory, "control.json"))
            controller = AdaptiveController(
                "unused", state, allow_printer_commands=False)
            with self.assertRaises(PermissionError):
                controller.arm(ARM_PHRASE)
            unlocked = AdaptiveController(
                "unused", state, allow_printer_commands=True)
            with self.assertRaises(ValueError):
                unlocked.arm("yes")
            unlocked.update_config({
                "mode": "dry_run",
                "adaptive_pa_enabled": True,
            })
            result = unlocked.arm(ARM_PHRASE)
            self.assertTrue(result["armed"])
            self.assertEqual("apply", result["mode"])
            result = unlocked.disarm()
            self.assertFalse(result["armed"])
            self.assertEqual("dry_run", result["mode"])

    def test_persisted_apply_mode_degrades_to_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            state = pathlib.Path(directory, "control.json")
            state.write_text('{"mode":"apply"}', encoding="utf-8")
            controller = AdaptiveController("unused", str(state))
            self.assertEqual("dry_run", controller.status()["mode"])

    def test_invalid_or_aggressive_config_is_rejected(self):
        with self.assertRaises(ValueError):
            validated_config(DEFAULT_CONFIG, {"adaptive_pa_enabled": 1})
        with self.assertRaises(ValueError):
            validated_config(DEFAULT_CONFIG, {"pa_step": 0.1})
        with self.assertRaises(ValueError):
            validated_config(DEFAULT_CONFIG, {
                "retract_min_mm": 2.0,
                "retract_max_mm": 1.0,
            })
        with self.assertRaises(ValueError):
            validated_config(DEFAULT_CONFIG, {"surprise": True})

    def test_pa_change_is_bounded_and_restored_on_disarm(self):
        sent = []
        with tempfile.TemporaryDirectory() as directory:
            controller = AdaptiveController(
                "unused", str(pathlib.Path(directory, "control.json")),
                allow_printer_commands=True, send_gcode=sent.append)
            controller.update_config({
                "mode": "dry_run",
                "adaptive_pa_enabled": True,
            })
            controller.arm(ARM_PHRASE)
            controller._maybe_apply({
                "print_state": "printing",
                "pressure_advance": 0.03,
            }, {
                "reason": "ok",
                "suggested_pa": 0.20,
                "pa_context_eligible": True,
            })
            self.assertEqual(
                "SET_PRESSURE_ADVANCE ADVANCE=0.040000", sent[0])
            result = controller.update_config({"mode": "off"})
            self.assertEqual(
                "SET_PRESSURE_ADVANCE ADVANCE=0.030000", sent[1])
            self.assertEqual("off", result["mode"])

    def test_auto_retract_requires_firmware_mode_and_restores(self):
        sent = []
        with tempfile.TemporaryDirectory() as directory:
            controller = AdaptiveController(
                "unused", str(pathlib.Path(directory, "control.json")),
                allow_printer_commands=True, send_gcode=sent.append)
            controller.update_config({
                "mode": "dry_run",
                "auto_retract_enabled": True,
            })
            with self.assertRaises(ValueError):
                controller.arm(ARM_PHRASE)
            controller.firmware_retraction_available = True
            controller.current_retract = 0.8
            controller.arm(ARM_PHRASE)
            controller._maybe_apply({
                "print_state": "printing",
                "pressure_advance": 0.03,
            }, {
                "reason": "ok",
                "suggested_retract_mm": 0.9,
            })
            self.assertEqual(
                "SET_RETRACTION RETRACT_LENGTH=0.900", sent[0])
            controller.disarm()
            self.assertEqual(
                "SET_RETRACTION RETRACT_LENGTH=0.800", sent[1])

    def test_invalid_sensor_evidence_never_sends_a_command(self):
        sent = []
        with tempfile.TemporaryDirectory() as directory:
            controller = AdaptiveController(
                "unused", str(pathlib.Path(directory, "control.json")),
                allow_printer_commands=True, send_gcode=sent.append)
            controller.update_config({
                "mode": "dry_run",
                "adaptive_pa_enabled": True,
            })
            controller.arm(ARM_PHRASE)
            controller._maybe_apply({
                "print_state": "printing",
                "pressure_advance": 0.03,
            }, {
                "reason": "force_stale",
                "suggested_pa": 0.04,
            })
            self.assertEqual([], sent)

    def test_pa_apply_is_suppressed_without_eligible_context(self):
        sent = []
        with tempfile.TemporaryDirectory() as directory:
            controller = AdaptiveController(
                "unused", str(pathlib.Path(directory, "control.json")),
                allow_printer_commands=True, send_gcode=sent.append)
            controller.update_config({
                "mode": "dry_run",
                "adaptive_pa_enabled": True,
            })
            controller.arm(ARM_PHRASE)
            controller._maybe_apply({
                "print_state": "printing",
                "pressure_advance": 0.03,
            }, {
                "reason": "ok",
                "suggested_pa": 0.04,
                "pa_context_eligible": False,
            })
            self.assertEqual([], sent)

    def test_controller_resolves_context_at_current_print_time(self):
        marker = encode_context_marker({
            "layer": 7,
            "z_mm": 1.6,
            "feature": "External perimeter",
            "object": "cube",
        })
        with tempfile.TemporaryDirectory() as directory:
            now = time.monotonic()
            now_ns = time.monotonic_ns()
            controller = AdaptiveController(
                "unused", str(pathlib.Path(directory, "control.json")))
            live = {
                "clock": {
                    "host_monotonic": now,
                    "print_time": 100.0,
                },
                "gcode_context": {"transitions": [{
                    "sequence": 1,
                    "print_time": 99.0,
                    "event": "context",
                    "value": marker,
                }]},
                "extruder_motion": {"segments": [{
                    "print_time": 99.0,
                    "duration_s": 2.0,
                    "start_velocity_mm_s": 2.0,
                    "acceleration_mm_s2": 0.0,
                    "direction": 1.0,
                    "pressure_advance_active": True,
                }]},
                "toolhead_motion": {"segments": [{
                    "print_time": 99.0,
                    "duration_s": 2.0,
                    "start_velocity_mm_s": 80.0,
                    "acceleration_mm_s2": 0.0,
                }]},
                "force": {
                    "host_monotonic_ns": now_ns,
                    "filtered": 1000.0,
                    "raw": 1000.0,
                },
                "sample_rates_hz": {"force": 2500.0},
                "acceleration": {
                    "x_mm_s2": 0.0,
                    "y_mm_s2": 0.0,
                    "z_mm_s2": 0.0,
                    "errors": 0,
                    "overflows": 0,
                },
                "printer": {
                    "print_state": "printing",
                    "temperature_c": 210.0,
                    "target_c": 210.0,
                    "pressure_advance": 0.03,
                },
            }
            controller.step(
                live=live, current_retract_mm=0.8)
            status = controller.status()
            self.assertEqual(7, status["gcodeContext"]["layer"])
            self.assertTrue(status["paContextEligible"])
            self.assertAlmostEqual(2.0, status["extruderVelocityMmS"])
            self.assertAlmostEqual(80.0, status["toolheadVelocityMmS"])
            self.assertAlmostEqual(
                4.81056375, status["volumetricFlowMm3S"], places=5)


if __name__ == "__main__":
    unittest.main()
