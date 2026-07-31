import unittest

from autopa.pa_runner import PaSweepRunner


def printer_status(state="standby", pressure_advance=0.04):
    status = {"print_stats": {"state": state}}
    if pressure_advance is not None:
        status["extruder"] = {"pressure_advance": pressure_advance}
    return status


def run_payload(**overrides):
    payload = {
        "phrase": "AUTOPA VALIDIEREN",
        "k_start": 0.0,
        "k_stop": 0.05,
        "k_step": 0.01,
        "cycles": 4,
    }
    payload.update(overrides)
    return payload


class PaSweepRunnerTest(unittest.TestCase):
    def make_runner(self, allow=True):
        scripts = []
        runner = PaSweepRunner(
            allow_printer_commands=allow,
            send_script=scripts.append)
        return runner, scripts

    def test_run_sends_marked_script_and_restores_current_value(self):
        runner, scripts = self.make_runner()
        status = runner.run(run_payload(), printer_status=printer_status())
        self.assertEqual(len(scripts), 1)
        script = scripts[0]
        self.assertEqual(script.count("SET_PRESSURE_ADVANCE ADVANCE="), 7)
        self.assertIn("AUTOPA_VALIDATE X_TRAVEL=8.0000 MIN_Z=10.0000", script)
        self.assertTrue(
            script.rstrip().endswith("; End AutoPA sweep"))
        self.assertIn("SET_PRESSURE_ADVANCE ADVANCE=0.040000", script)
        self.assertEqual(
            status["lastRun"]["kValues"], [0.0, 0.01, 0.02, 0.03, 0.04, 0.05])
        self.assertEqual(status["lastRun"]["restoreAdvance"], 0.04)
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

    def test_missing_pressure_advance_is_rejected(self):
        runner, scripts = self.make_runner()
        with self.assertRaises(ValueError):
            runner.run(
                run_payload(),
                printer_status=printer_status(pressure_advance=None))
        self.assertEqual(scripts, [])

    def test_out_of_range_pressure_advance_is_rejected(self):
        runner, scripts = self.make_runner()
        with self.assertRaises(ValueError):
            runner.run(
                run_payload(),
                printer_status=printer_status(pressure_advance=0.5))
        self.assertEqual(scripts, [])

    def test_bounds_and_value_count_are_enforced(self):
        runner, scripts = self.make_runner()
        for overrides in (
                {"k_step": 0.0001},
                {"k_start": 0.1, "k_stop": 0.05},
                {"k_stop": 0.21},
                {"cycles": 2},
                {"k_start": 0.0, "k_stop": 0.2, "k_step": 0.005}):
            with self.assertRaises(ValueError):
                runner.run(
                    run_payload(**overrides),
                    printer_status=printer_status())
        self.assertEqual(scripts, [])

    def test_position_and_prime_are_embedded_and_bounded(self):
        runner, scripts = self.make_runner()
        status = runner.run(
            run_payload(start_z=50.0, prime_e=4.0),
            printer_status=printer_status())
        script = scripts[0]
        self.assertIn("G1 Z50.0000 F600", script)
        self.assertIn("G1 E4.00000 F300", script)
        self.assertEqual(status["lastRun"]["startZMm"], 50.0)
        self.assertEqual(status["lastRun"]["primeEMm"], 4.0)
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
        self.assertEqual(status["lastRun"]["applyBound"], 0.09)
        status = runner.run(
            run_payload(auto_apply=False, apply_bound=0.02),
            printer_status=printer_status())
        self.assertFalse(status["lastRun"]["autoApply"])
        self.assertEqual(status["lastRun"]["applyBound"], 0.02)
        with self.assertRaises(ValueError):
            runner.run(
                run_payload(apply_bound=0.5),
                printer_status=printer_status())

    def test_apply_within_bound_sends_runtime_command(self):
        runner, scripts = self.make_runner()
        runner.run(run_payload(), printer_status=printer_status())
        runner._printer_status = lambda: printer_status(pressure_advance=0.04)
        status = runner.apply_recommendation(0.07, source="ds1")
        self.assertEqual(scripts[-1], "SET_PRESSURE_ADVANCE ADVANCE=0.070000")
        apply = status["lastApply"]
        self.assertTrue(apply["applied"])
        self.assertTrue(apply["runtimeOnly"])
        self.assertEqual(apply["previous"], 0.04)
        self.assertEqual(apply["appliedValue"], 0.07)
        self.assertEqual(apply["bound"], 0.09)

    def test_apply_outside_bound_is_skipped(self):
        runner, scripts = self.make_runner()
        runner.run(run_payload(), printer_status=printer_status())
        runner._printer_status = lambda: printer_status(pressure_advance=0.04)
        status = runner.apply_recommendation(0.18, source="ds1")
        self.assertEqual(len(scripts), 1)
        apply = status["lastApply"]
        self.assertFalse(apply["applied"])
        self.assertEqual(apply["reason"], "outside_bounds")
        self.assertEqual(apply["printerAction"], "none")

    def test_apply_requires_printer_commands(self):
        runner, _ = self.make_runner(allow=False)
        with self.assertRaises(PermissionError):
            runner.apply_recommendation(0.06)

    def test_record_apply_skip(self):
        runner, _ = self.make_runner()
        status = runner.record_apply_skip("no_capture_dataset")
        self.assertFalse(status["lastApply"]["applied"])
        self.assertEqual(
            status["lastApply"]["reason"], "no_capture_dataset")


if __name__ == "__main__":
    unittest.main()
