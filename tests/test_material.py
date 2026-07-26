import unittest

from autopa.material import compare_material_temperatures


def material_result(temperature, cost, variation, snr, pa):
    return {
        "dataset": "test-%s" % temperature,
        "status": "consistent",
        "temperature": {"median_temperature_c": temperature},
        "metrics": {
            "pa_cost": cost,
            "amplitude_mad_fraction": variation,
            "signal_to_noise_mad": snr,
            "pressure_advance": pa,
        },
        "pressure_loss_events": 0,
    }


class MaterialTemperatureTest(unittest.TestCase):
    def test_interior_best_temperature_is_recommended(self):
        result = compare_material_temperatures([
            material_result(200, 0.8, 0.20, 10, 0.05),
            material_result(210, 0.2, 0.05, 30, 0.04),
            material_result(220, 0.6, 0.12, 20, 0.03),
        ])
        self.assertTrue(result["available"])
        self.assertEqual(result["recommended_temperature_c"], 210)
        self.assertEqual(result["recommended_pressure_advance"], 0.04)

    def test_boundary_best_requests_wider_range(self):
        result = compare_material_temperatures([
            material_result(200, 0.1, 0.03, 30, 0.05),
            material_result(210, 0.4, 0.10, 20, 0.04),
            material_result(220, 0.8, 0.20, 10, 0.03),
        ])
        self.assertTrue(result["available"])
        self.assertIsNone(result["recommended_temperature_c"])
        self.assertTrue(
            result["boundary_result_requires_wider_test_range"])

    def test_three_temperatures_are_required(self):
        result = compare_material_temperatures([
            material_result(200, 0.2, 0.05, 20, 0.04),
            material_result(210, 0.3, 0.06, 20, 0.03),
        ])
        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()
