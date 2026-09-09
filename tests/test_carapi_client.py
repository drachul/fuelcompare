import os
import unittest
from unittest.mock import Mock, patch

import requests

from server import carapi_client


class CarApiClientTests(unittest.TestCase):
    def setUp(self):
        carapi_client._cache = carapi_client._TTLCache()
        carapi_client._jwt = ""
        carapi_client._jwt_expires_at = 0
        carapi_client._auth_retry_after = 0
        self.env = patch.dict(
            os.environ,
            {"CARAPI_API_TOKEN": "", "CARAPI_API_SECRET": ""},
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def response(rows):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": rows}
        return response

    @patch.object(carapi_client._session, "get")
    def test_selects_clear_mpg_match_and_converts_gallons(self, get):
        get.return_value = self.response(
            [
                {
                    "year": 2018,
                    "make": "Toyota",
                    "model": "Camry",
                    "trim_description": "LE 4dr Sedan (2.5L 4cyl 8A)",
                    "fuel_tank_capacity": "16.0",
                    "epa_city_mpg": 28,
                    "epa_highway_mpg": 39,
                },
                {
                    "year": 2018,
                    "make": "Toyota",
                    "model": "Camry",
                    "trim_description": "L 4dr Sedan (2.5L 4cyl 8A)",
                    "fuel_tank_capacity": "14.5",
                    "epa_city_mpg": 29,
                    "epa_highway_mpg": 41,
                },
                {
                    "year": 2018,
                    "make": "Toyota",
                    "model": "Camry",
                    "trim_description": "XLE 4dr Sedan (3.5L 6cyl 8A)",
                    "fuel_tank_capacity": "16.0",
                    "epa_city_mpg": 22,
                    "epa_highway_mpg": 33,
                },
            ]
        )

        result = carapi_client.find_tank_capacity(
            "2018",
            "Toyota",
            "Camry",
            cylinders="4",
            displacement_l="2.5",
            city_mpg="29",
            highway_mpg="41",
            transmission="Automatic (S8)",
        )

        self.assertEqual(result["capacity_l"], 54.9)
        self.assertIn("L 4dr Sedan", result["matched_trim"])
        self.assertFalse(result["ambiguous"])
        self.assertIn(60.6, [match["capacity_l"] for match in result["matches"]])
        self.assertNotIn("Authorization", get.call_args.kwargs["headers"])
        self.assertEqual(get.call_args.kwargs["params"]["limit"], 100)

    @patch.object(carapi_client._session, "get")
    def test_does_not_autofill_when_different_capacities_tie(self, get):
        get.return_value = self.response(
            [
                {
                    "year": 2018,
                    "make": "Example",
                    "model": "One",
                    "trim_description": "Alpha (2.0L 4cyl 6A)",
                    "fuel_tank_capacity": "12",
                    "epa_city_mpg": 25,
                    "epa_highway_mpg": 32,
                },
                {
                    "year": 2018,
                    "make": "Example",
                    "model": "One",
                    "trim_description": "Beta (2.0L 4cyl 6A)",
                    "fuel_tank_capacity": "14",
                    "epa_city_mpg": 25,
                    "epa_highway_mpg": 32,
                },
            ]
        )

        result = carapi_client.find_tank_capacity(
            "2018", "Example", "One", "4", "2.0", "25", "32", "Automatic"
        )

        self.assertIsNone(result["capacity_l"])
        self.assertTrue(result["ambiguous"])
        self.assertEqual(len(result["matches"]), 2)

    @patch.object(carapi_client._session, "get")
    def test_network_failure_is_a_cached_miss(self, get):
        get.side_effect = requests.Timeout("timed out")

        first = carapi_client.find_tank_capacity("2018", "Toyota", "Camry")
        second = carapi_client.find_tank_capacity("2018", "Toyota", "Camry")

        self.assertIsNone(first)
        self.assertIsNone(second)
        get.assert_called_once()

    @patch.object(carapi_client._session, "get")
    def test_uses_base_model_before_epa_variant_name(self, get):
        get.return_value = self.response(
            [
                {
                    "year": 2018,
                    "make": "Toyota",
                    "model": "Camry",
                    "trim_description": "Hybrid LE (2.5L 4cyl CVT)",
                    "fuel_tank_capacity": "13",
                    "epa_city_mpg": 51,
                    "epa_highway_mpg": 53,
                }
            ]
        )

        result = carapi_client.find_tank_capacity(
            "2018", "Toyota", "Camry Hybrid LE", base_model="Camry"
        )

        self.assertEqual(result["capacity_l"], 49.2)
        self.assertEqual(get.call_args.kwargs["params"]["model"], "Camry")


if __name__ == "__main__":
    unittest.main()
