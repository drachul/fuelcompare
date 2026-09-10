import os
import tempfile
import unittest
from unittest.mock import patch

from server import create_app


EPA_VEHICLE = {
    "id": "12345",
    "year": "2018",
    "make": "Toyota",
    "model": "Camry",
    "base_model": "Camry",
    "trany": "Automatic (S8)",
    "cylinders": "4",
    "displ": "2.5",
    "fuel_type": "regular",
    "city_mpg": 29.0,
    "highway_mpg": 41.0,
    "city_l_100km": 8.111,
    "highway_l_100km": 5.737,
}


class VehicleCacheRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = os.path.join(self.temp_dir.name, "vehicles.db")

    def app(self):
        return create_app({
            "TESTING": True,
            "VEHICLE_DB_PATH": self.database_path,
        })

    @patch("server.routes.epa_client.get_vehicle")
    def test_epa_vehicle_is_reused_by_a_new_app_instance(self, get_vehicle):
        get_vehicle.return_value = EPA_VEHICLE.copy()
        first = self.app().test_client().get("/api/vehicle/12345")

        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.get_json()["cached"])
        get_vehicle.assert_called_once_with("12345")

        get_vehicle.reset_mock()
        second = self.app().test_client().get("/api/vehicle/12345")

        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.get_json()["cached"])
        self.assertEqual(second.get_json()["city_l_100km"], 8.111)
        get_vehicle.assert_not_called()

    @patch("server.routes.epa_client.get_vehicle")
    def test_tank_lookup_is_merged_into_vehicle_cache(self, get_vehicle):
        get_vehicle.return_value = EPA_VEHICLE.copy()
        client = self.app().test_client()
        client.get("/api/vehicle/12345")
        query = (
            "/api/tank-size?year=2018&make=Toyota&model=Camry"
            "&vehicle_id=12345"
        )

        with patch("server.routes.carapi_client.find_tank_capacity") as lookup:
            lookup.return_value = {
                "capacity_l": 54.9,
                "matched_trim": "LE 2.5L",
                "matches": [],
                "ambiguous": False,
                "source": "CarAPI",
            }
            first = client.get(query)

        self.assertEqual(first.get_json()["capacity_l"], 54.9)

        with patch("server.routes.carapi_client.find_tank_capacity") as lookup:
            second = self.app().test_client().get(query)
            lookup.assert_not_called()

        self.assertTrue(second.get_json()["cached"])
        self.assertEqual(second.get_json()["capacity_l"], 54.9)

    @patch("server.routes.epa_client.get_vehicle")
    def test_ambiguous_tank_candidates_are_cached(self, get_vehicle):
        get_vehicle.return_value = EPA_VEHICLE.copy()
        client = self.app().test_client()
        client.get("/api/vehicle/12345")
        query = (
            "/api/tank-size?year=2018&make=Toyota&model=Camry"
            "&vehicle_id=12345"
        )
        ambiguous = {
            "capacity_l": None,
            "matched_trim": "",
            "matches": [
                {"capacity_l": 54.9, "matched_trim": "LE"},
                {"capacity_l": 60.6, "matched_trim": "XSE"},
            ],
            "ambiguous": True,
            "source": "CarAPI",
        }

        with patch("server.routes.carapi_client.find_tank_capacity", return_value=ambiguous):
            first = client.get(query)
        with patch("server.routes.carapi_client.find_tank_capacity") as lookup:
            second = self.app().test_client().get(query)
            lookup.assert_not_called()

        self.assertEqual(first.get_json()["matches"], ambiguous["matches"])
        self.assertTrue(second.get_json()["cached"])
        self.assertEqual(second.get_json()["matches"], ambiguous["matches"])

    def test_heavy_duty_manual_comparison_is_saved_and_can_be_loaded(self):
        payload = {
            "distance": {"value": 12000, "unit": "km", "period": "year"},
            "weighting": {"city": 50, "highway": 50},
            "price_unit": "liter",
            "prices": {
                "regular": 1.7,
                "midgrade": 1.8,
                "premium": 1.9,
                "diesel": 1.8,
            },
            "vehicles": [{
                "label": "2022 Ford F-350 — 6.7L diesel, 4x4",
                "year": "2022",
                "make": "Ford",
                "model": "F-350",
                "trim": "6.7L diesel, 4x4",
                "city_l_100km": 18.093,
                "highway_l_100km": 18.093,
                "fuel_type": "diesel",
                "tank_size": 128,
                "tank_unit": "liter",
            }],
        }
        client = self.app().test_client()

        response = client.post("/api/compare", json=payload)
        saved = client.get("/api/saved-vehicles").get_json()
        loaded = client.get(f"/api/saved-vehicle/{saved[0]['record_id']}").get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["label"], "2022 Ford F-350 — 6.7L diesel, 4x4")
        self.assertEqual(loaded["make"], "Ford")
        self.assertEqual(loaded["model"], "F-350")
        self.assertEqual(loaded["tank_size"], 128)
        self.assertEqual(loaded["city_l_100km"], 18.093)

    @patch("server.routes.epa_client.get_vehicle")
    def test_manual_corrections_override_but_do_not_discard_epa_data(self, get_vehicle):
        get_vehicle.return_value = EPA_VEHICLE.copy()
        client = self.app().test_client()
        looked_up = client.get("/api/vehicle/12345").get_json()
        payload = {
            "distance": {"value": 12000, "unit": "km", "period": "year"},
            "weighting": {"city": 50, "highway": 50},
            "price_unit": "liter",
            "prices": {"regular": 1.7},
            "vehicles": [{
                "record_id": looked_up["record_id"],
                "epa_vehicle_id": "12345",
                "label": "2018 Toyota Camry — corrected",
                "year": "2018",
                "make": "Toyota",
                "model": "Camry",
                "trim": "corrected",
                "city_l_100km": 8.4,
                "highway_l_100km": 5.9,
                "fuel_type": "regular",
                "tank_size": 55,
                "tank_unit": "liter",
            }],
        }

        response = client.post("/api/compare", json=payload)
        cached = self.app().test_client().get("/api/vehicle/12345").get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(cached["city_l_100km"], 8.4)
        self.assertEqual(cached["tank_size"], 55)
        self.assertEqual(cached["trany"], "Automatic (S8)")
        self.assertTrue(cached["cached"])


if __name__ == "__main__":
    unittest.main()
