import unittest

from autopa.retract_runner import RetractSweepRunner


def printer_status(state="standby", retract_length=0.5, retract_speed=120.0):
    status = {"print_stats": {"state": state}}
    if retract_length is not None:
        status["firmware_retraction"] = {
            "retract_length": retract_length,
            "retract_speed": retract_speed,
        }
    return status


def run_payload(**overrides):
    payload = {
        "phrase": "AUTOPA VALIDIEREN",
        "r_start": 0.2,
        "r_stop": 1.4,
        "r_step": 0.2,
        "cycles": 5,
    }
    payload.update(overrides)
    return payload


class RetractSweepRunnerTest(unittest.TestCase):
    def make_runner(self, allow=True):
        scripts = []
        runner = RetractSweepRunner(
            allow_printer_commands=allow,
            send_script=scripts.append)
        return runner, scripts

    def test_run_sends_marked_script_and_restores_current_value(self):
        runner, scripts = self.make_runner()
        status = runner.run(run_payload(), printer_status=printer_status())
        self.assertEqual(len(scripts), 1)
        script = scripts[0]
        self.assertEqual(script.count("\nG10\n"), 35)
        self.assertIn("AUTOPA_VALIDATE X_TRAVEL=8.0000 MIN_Z=10.0000", script)
        self.assertIn("SET_RETRACTION RETRACT_LENGTH=0.5000", script)
        self.assertEqual(
            status["lastRun"]["retractValues"],
            [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4])
        self.assertEqual(status["lastRun"]["restoreRetractMm"], 0.5)
        self.assertIsNone(status["lastError"])

    def test_wrong_phrase_is_rejected(self):
        runner, scripts = self.make_runner()
        with self.assertRaises(ValueError):
            runner.run(
                run_payload(phrase="falsch"),
                printer_status=printer_status())
        self.assertEqual(scripts, [])

    def test_server_lock_blocks_run(self):
        runner, scripts = self.make_runner(allow=False)
        with self.assertRaises(PermissionError):
            runner.run(run_payload(), printer_status=printer_status())
        self.assertEqual(scripts, [])

    def test_printing_printer_is_rejected(self):
        runner, scripts = self.make_runner()
        with self.assertRaises(ValueError):
            runner.run(
                run_payload(),
                printer_status=printer_status(state="printing"))
        self.assertEqual(scripts, [])

    def test_missing_firmware_retraction_is_rejected(self):
        runner, scripts = self.make_runner()
        with self.assertRaises(ValueError):
            runner.run(
                run_payload(),
                printer_status=printer_status(retract_length=None))
        self.assertEqual(scripts, [])

    def test_bounds_and_value_count_are_enforced(self):
        runner, scripts = self.make_runner()
        for overrides in (
                {"r_step": 0.001},
                {"r_start": 1.0, "r_stop": 0.5},
                {"cycles": 2},
                {"r_start": 0.05, "r_stop": 5.0, "r_step": 0.05}):
            with self.assertRaises(ValueError):
                runner.run(
                    run_payload(**overrides),
                    printer_status=printer_status())
        self.assertEqual(scripts, [])

    def test_position_and_prime_are_embedded_and_bounded(self):
        runner, scripts = self.make_runner()
        status = runner.run(
            run_payload(start_z=50.0, prime_e=5.0),
            printer_status=printer_status())
        script = scripts[0]
        self.assertIn("G1 Z50.0000 F600", script)
        self.assertIn("G1 E5.00000 F300", script)
        self.assertEqual(status["lastRun"]["startZMm"], 50.0)
        self.assertEqual(status["lastRun"]["primeEMm"], 5.0)
        for overrides in (
                {"start_z": 5.0},
                {"start_z": 400.0},
                {"prime_e": 25.0},
                {"start_x": -1.0},
                {"start_y": 600.0}):
            with self.assertRaises(ValueError):
                runner.run(
                    run_payload(**overrides),
                    printer_status=printer_status())
        self.assertEqual(len(scripts), 1)

    def test_disabled_runner_status_shape(self):
        runner, _ = self.make_runner(allow=False)
        status = runner.status()
        self.assertFalse(status["allowPrinterCommands"])
        self.assertEqual(status["printerAction"], "none")
        self.assertIsNone(status["lastApply"])

    def test_run_records_auto_apply_and_bound(self):
        runner, _ = self.make_runner()
        status = runner.run(run_payload(), printer_status=printer_status())
        self.assertTrue(status["lastRun"]["autoApply"])
        self.assertEqual(status["lastRun"]["applyBoundMm"], 1.5)
        status = runner.run(
            run_payload(auto_apply=False, apply_bound=0.8),
            printer_status=printer_status())
        self.assertFalse(status["lastRun"]["autoApply"])
        self.assertEqual(status["lastRun"]["applyBoundMm"], 0.8)
        with self.assertRaises(ValueError):
            runner.run(
                run_payload(apply_bound=4.0),
                printer_status=printer_status())

    def test_apply_within_bound_sends_runtime_command(self):
        runner, scripts = self.make_runner()
        runner.run(run_payload(), printer_status=printer_status())
        runner._printer_status = lambda: printer_status(retract_length=0.5)
        status = runner.apply_recommendation(1.2, source="ds1")
        self.assertEqual(scripts[-1], "SET_RETRACTION RETRACT_LENGTH=1.200")
        apply = status["lastApply"]
        self.assertTrue(apply["applied"])
        self.assertTrue(apply["runtimeOnly"])
        self.assertEqual(apply["previousMm"], 0.5)
        self.assertEqual(apply["appliedMm"], 1.2)
        self.assertEqual(apply["boundMm"], 1.5)
        self.assertEqual(apply["source"], "ds1")

    def test_apply_outside_bound_is_skipped(self):
        runner, scripts = self.make_runner()
        runner.run(run_payload(), printer_status=printer_status())
        runner._printer_status = lambda: printer_status(retract_length=0.5)
        status = runner.apply_recommendation(3.0, source="ds1")
        self.assertEqual(len(scripts), 1)
        apply = status["lastApply"]
        self.assertFalse(apply["applied"])
        self.assertEqual(apply["reason"], "outside_bounds")
        self.assertEqual(apply["printerAction"], "none")

    def test_apply_respects_custom_bound(self):
        runner, scripts = self.make_runner()
        runner.run(
            run_payload(apply_bound=0.3),
            printer_status=printer_status())
        runner._printer_status = lambda: printer_status(retract_length=0.5)
        status = runner.apply_recommendation(1.0)
        self.assertFalse(status["lastApply"]["applied"])
        status = runner.apply_recommendation(0.7)
        self.assertTrue(status["lastApply"]["applied"])
        self.assertEqual(scripts[-1], "SET_RETRACTION RETRACT_LENGTH=0.700")

    def test_apply_requires_printer_commands(self):
        runner, _ = self.make_runner(allow=False)
        with self.assertRaises(PermissionError):
            runner.apply_recommendation(1.0)

    def test_record_apply_skip(self):
        runner, _ = self.make_runner()
        status = runner.record_apply_skip("no_recommendation", source="ds1")
        apply = status["lastApply"]
        self.assertFalse(apply["applied"])
        self.assertEqual(apply["reason"], "no_recommendation")
        self.assertEqual(apply["printerAction"], "none")


if __name__ == "__main__":
    unittest.main()
