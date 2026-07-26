import unittest

from autopa.filament import detect_pressure_loss


def synthetic_print(drop_start=None, drop_stop=None):
    rows = []
    step = 0.01
    for index in range(1200):
        time = index * step
        velocity = 0.0 if time < 2.0 or time >= 10.0 else 2.0
        force = 1000.0
        if velocity > 0:
            force = 2000.0
        if (drop_start is not None and drop_start <= time
                and (drop_stop is None or time < drop_stop)):
            force = 1005.0
        force += (index % 5) - 2
        rows.append({
            "print_time": time,
            "force": force,
            "e_velocity": velocity,
        })
    return rows


class FilamentDetectionTest(unittest.TestCase):
    def test_sustained_pressure_loss_is_detected(self):
        result = detect_pressure_loss(
            synthetic_print(drop_start=7.0), confirm_seconds=1.0)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(
            result["events"][0]["event"], "lost_extrusion_pressure")
        self.assertEqual(
            result["events"][0]["printer_action"], "none")

    def test_short_pressure_dip_is_not_detected(self):
        result = detect_pressure_loss(
            synthetic_print(drop_start=7.0, drop_stop=7.4),
            confirm_seconds=1.0)
        self.assertTrue(result["available"])
        self.assertEqual(result["events"], [])

    def test_no_extrusion_reference_is_unavailable(self):
        rows = synthetic_print()
        for row in rows:
            row["e_velocity"] = 0.0
            row["force"] = 1000.0
        result = detect_pressure_loss(rows)
        self.assertFalse(result["available"])
        self.assertEqual(
            result["reason"], "insufficient_positive_extrusion")


if __name__ == "__main__":
    unittest.main()
