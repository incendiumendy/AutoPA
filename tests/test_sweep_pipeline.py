import os
import tempfile
import time
import unittest

from autopa.dashboard import DashboardData
from autopa.pa_runner import PaSweepRunner
from autopa.retract_runner import RetractSweepRunner


RETRACT_PAYLOAD = {
    "phrase": "AUTOPA VALIDIEREN",
    "r_start": 0.2,
    "r_stop": 1.4,
    "r_step": 0.2,
    "cycles": 5,
}
PA_PAYLOAD = {
    "phrase": "AUTOPA VALIDIEREN",
    "k_start": 0.0,
    "k_stop": 0.05,
    "k_step": 0.01,
    "cycles": 4,
}


def retract_printer_status(retract_length=0.5):
    return {
        "print_stats": {"state": "standby"},
        "firmware_retraction": {
            "retract_length": retract_length,
            "retract_speed": 120.0,
        },
    }


def pa_printer_status(pressure_advance=0.04):
    return {
        "print_stats": {"state": "standby"},
        "extruder": {"pressure_advance": pressure_advance},
    }


class FakeCaptureManager:
    def __init__(self, output_root, dataset="sweep-ds"):
        self.output_root = output_root
        self.dataset = dataset
        self.started = []
        self.stopped = []
        self.can_start = True
        os.makedirs(os.path.join(output_root, dataset), exist_ok=True)

    def status(self):
        return {
            "canStart": self.can_start and not self.started,
            "active": bool(self.started) and not self.stopped,
            "dataset": self.dataset,
        }

    def start(self, print_state, name):
        self.started.append((print_state, name))
        return self.status()

    def stop(self, reason="user"):
        self.stopped.append(reason)
        return self.status()


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class SweepPipelineTest(unittest.TestCase):
    def make_data(self, tmp, analyzer_result, kind="retract"):
        scripts = []
        if kind == "retract":
            runner = RetractSweepRunner(
                allow_printer_commands=True,
                send_script=scripts.append)
            runner._printer_status = retract_printer_status
            analyzer = lambda dataset_dir: analyzer_result
            kwargs = {"retract_analyzer": analyzer}
        else:
            runner = PaSweepRunner(
                allow_printer_commands=True,
                send_script=scripts.append)
            runner._printer_status = pa_printer_status
            analyzer = lambda dataset_dir: analyzer_result
            kwargs = {"pa_analyzer": analyzer}
        manager = FakeCaptureManager(tmp)
        quality_calls = []
        align_calls = []
        data = DashboardData(
            "http://127.0.0.1:7125",
            os.path.join(tmp, "live.json"),
            capture_manager=manager,
            sweep_runner=runner if kind == "retract" else None,
            pa_sweep_runner=runner if kind == "pa" else None,
            quality_fn=lambda dataset_dir: quality_calls.append(dataset_dir),
            sleep_fn=lambda seconds: None,
            align_fn=lambda dataset_dir: align_calls.append(dataset_dir),
            **kwargs)
        return data, runner, manager, scripts, (align_calls, quality_calls)

    def test_retract_pipeline_applies_within_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, runner, manager, scripts, calls = self.make_data(
                tmp, {"recommendation": {"retract_length_mm": 1.2}})
            align_calls, quality_calls = calls
            data.run_sweep(dict(RETRACT_PAYLOAD))
            self.assertEqual(manager.started, [("standby", "retract-sweep")])
            self.assertTrue(
                wait_for(lambda: runner.last_apply is not None))
            apply = runner.last_apply
            self.assertTrue(apply["applied"])
            self.assertEqual(apply["appliedMm"], 1.2)
            self.assertEqual(apply["source"], "sweep-ds")
            self.assertEqual(manager.stopped, ["sweep_finished"])
            self.assertEqual(
                scripts[-1], "SET_RETRACTION RETRACT_LENGTH=1.200")
            self.assertEqual(len(align_calls), 1)
            self.assertEqual(len(quality_calls), 1)

    def test_pa_pipeline_applies_within_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, runner, manager, scripts, _ = self.make_data(
                tmp, {"recommendation": {"pressure_advance": 0.07}},
                kind="pa")
            data.run_pa_sweep(dict(PA_PAYLOAD))
            self.assertTrue(
                wait_for(lambda: runner.last_apply is not None))
            self.assertTrue(runner.last_apply["applied"])
            self.assertEqual(runner.last_apply["appliedValue"], 0.07)
            self.assertEqual(
                scripts[-1], "SET_PRESSURE_ADVANCE ADVANCE=0.070000")

    def test_outside_bound_recommendation_is_not_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, runner, _, scripts, _ = self.make_data(
                tmp, {"recommendation": {"retract_length_mm": 4.0}})
            data.run_sweep(dict(RETRACT_PAYLOAD))
            self.assertTrue(
                wait_for(lambda: runner.last_apply is not None))
            self.assertFalse(runner.last_apply["applied"])
            self.assertEqual(
                runner.last_apply["reason"], "outside_bounds")
            self.assertEqual(len(scripts), 1)

    def test_missing_recommendation_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, runner, _, scripts, _ = self.make_data(
                tmp, {"recommendation": None})
            data.run_sweep(dict(RETRACT_PAYLOAD))
            self.assertTrue(
                wait_for(lambda: runner.last_apply is not None))
            self.assertEqual(
                runner.last_apply["reason"], "no_recommendation")
            self.assertEqual(len(scripts), 1)

    def test_speed_result_is_reported_instead_of_discarded(self):
        # A retraction-speed sweep produces a real result under a key this
        # pipeline cannot send. Reporting "no_recommendation" would be false,
        # and sending it as a length would be dangerous - so it becomes an
        # advisory the operator applies.
        with tempfile.TemporaryDirectory() as tmp:
            data, runner, _, scripts, _ = self.make_data(tmp, {
                "recommendation": {
                    "swept_variable": "retract_speed",
                    "retract_speed_mm_s": 45.0,
                    "cost": 0.21,
                    "cost_gap_to_second_best": 0.08,
                    "apply_automatically": False,
                },
            })
            data.run_sweep(dict(RETRACT_PAYLOAD))
            self.assertTrue(
                wait_for(lambda: runner.last_apply is not None))
            apply = runner.last_apply
            self.assertFalse(apply["applied"])
            self.assertTrue(apply["advisory"])
            self.assertEqual(apply["reason"], "manual_apply_required")
            self.assertEqual(apply["recommendedSpeedMmS"], 45.0)
            self.assertEqual(apply["sweptVariable"], "retract_speed")
            # Only the sweep itself was sent; nothing was applied.
            self.assertEqual(len(scripts), 1)
            self.assertNotIn("RETRACT_LENGTH=45", scripts[0])

    def test_auto_apply_disabled_skips_capture_and_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, runner, manager, _, _ = self.make_data(
                tmp, {"recommendation": {"retract_length_mm": 1.2}})
            payload = dict(RETRACT_PAYLOAD, auto_apply=False)
            data.run_sweep(payload)
            self.assertEqual(manager.started, [])
            self.assertIsNone(runner.last_apply)

    def test_rejected_run_stops_the_started_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, runner, manager, _, _ = self.make_data(
                tmp, {"recommendation": {"retract_length_mm": 1.2}})
            payload = dict(RETRACT_PAYLOAD, phrase="falsch")
            with self.assertRaises(ValueError):
                data.run_sweep(payload)
            self.assertEqual(manager.started, [("standby", "retract-sweep")])
            self.assertEqual(manager.stopped, ["sweep_rejected"])
            self.assertIsNone(runner.last_apply)

    def test_busy_capture_refuses_before_the_printer_moves(self):
        # A sweep that cannot own its capture produces nothing analysable:
        # the running capture is never finalised, so there are no markers.
        # It used to run anyway and report no_capture_dataset afterwards,
        # having extruded filament for nothing. Now it refuses up front.
        for kind in ("retract", "pa"):
            with tempfile.TemporaryDirectory() as tmp:
                data, runner, manager, scripts, _ = self.make_data(
                    tmp, {"recommendation": {"retract_length_mm": 1.2}},
                    kind=kind)
                manager.can_start = False
                manager.dataset = None
                run = data.run_sweep if kind == "retract" else data.run_pa_sweep
                payload = RETRACT_PAYLOAD if kind == "retract" else PA_PAYLOAD
                with self.assertRaises(ValueError) as raised:
                    run(dict(payload))
                self.assertIn("Live-Daten", str(raised.exception))
                # Nothing was sent and no capture was taken over.
                self.assertEqual(scripts, [], "%s sweep must not run" % kind)
                self.assertEqual(manager.started, [])
                self.assertIsNone(runner.last_apply)

    def test_capture_that_fails_to_start_never_analyzes_stale_data(self):
        # A recorder that is free but errors on start must not block a sweep
        # the operator already confirmed - only a busy one does. But the
        # manager keeps reporting the previous dataset name after a stop, so
        # the pipeline must not fall back to it: applying a value derived
        # from an unrelated earlier run is worse than applying nothing.
        with tempfile.TemporaryDirectory() as tmp:
            data, runner, manager, scripts, _ = self.make_data(
                tmp, {"recommendation": {"retract_length_mm": 1.2}})

            def boom(*args, **kwargs):
                raise RuntimeError("recorder unavailable")

            manager.start = boom
            data.run_sweep(dict(RETRACT_PAYLOAD))
            self.assertEqual(len(scripts), 1, "the sweep itself still runs")
            self.assertTrue(
                wait_for(lambda: runner.last_apply is not None))
            self.assertEqual(
                runner.last_apply["reason"], "no_capture_dataset")
            self.assertFalse(runner.last_apply["applied"])
            # Nothing beyond the sweep script reached the printer.
            self.assertEqual(len(scripts), 1)


if __name__ == "__main__":
    unittest.main()
