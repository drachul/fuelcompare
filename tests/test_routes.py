import os
import tempfile
import unittest
from unittest.mock import patch

from server import create_app
from server import epa_client, nrcan_client


class VehicleLookupRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.client = create_app({
            "TESTING": True,
            "VEHICLE_DB_PATH": os.path.join(self.temp_dir.name, "vehicles.db"),
        }).test_client()

    @patch("server.routes.epa_client.get_years", return_value=["2025", "1984"])
    @patch("server.routes.nrcan_client.get_years", return_value=["2026", "2025"])
    def test_years_merge_nrcan_and_epa_coverage(self, _nrcan, _epa):
        response = self.client.get("/api/years")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), ["2026", "2025", "1984"])

    @patch("server.routes.epa_client.get_makes", return_value=["Toyota", "Ford"])
    @patch("server.routes.nrcan_client.get_makes", return_value=["Toyota", "Acura"])
    def test_makes_are_merged_without_duplicates(self, _nrcan, _epa):
        response = self.client.get("/api/makes?year=2026")

        self.assertEqual(response.get_json(), ["Acura", "Ford", "Toyota"])

    @patch("server.routes.epa_client.get_models", return_value=["Camry"])
    @patch("server.routes.nrcan_client.get_models")
    def test_epa_remains_available_when_nrcan_fails(self, nrcan, _epa):
        nrcan.side_effect = nrcan_client.NrcanDataError("offline")

        response = self.client.get("/api/models?year=2026&make=Toyota")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), ["Camry"])

    @patch("server.routes.epa_client.get_trims")
    @patch("server.routes.nrcan_client.get_trims")
    def test_trim_options_identify_their_source(self, nrcan, epa):
        nrcan.return_value = [{"text": "2.5 L · AS8 — NRCan", "value": "nrcan:2026:abc"}]
        epa.return_value = [{"text": "2.5L Auto", "value": "12345"}]

        response = self.client.get("/api/trims?year=2026&make=Toyota&model=Camry")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            [
                {"text": "2.5 L · AS8 — NRCan", "value": "nrcan:2026:abc"},
                {"text": "2.5L Auto — EPA", "value": "12345"},
            ],
        )

    @patch("server.routes.epa_client.get_years")
    @patch("server.routes.nrcan_client.get_years")
    def test_lookup_returns_error_only_when_both_sources_fail(self, nrcan, epa):
        nrcan.side_effect = nrcan_client.NrcanDataError("NRCan offline")
        epa.side_effect = epa_client.EpaApiError("EPA offline")

        response = self.client.get("/api/years")

        self.assertEqual(response.status_code, 502)
        self.assertIn("NRCan offline", response.get_json()["error"])
        self.assertIn("EPA offline", response.get_json()["error"])


class TankSizeRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.client = create_app({
            "TESTING": True,
            "VEHICLE_DB_PATH": os.path.join(self.temp_dir.name, "vehicles.db"),
        }).test_client()

    def test_requires_vehicle_identity(self):
        response = self.client.get("/api/tank-size?year=2018")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "year, make and model are required")

    @patch("server.routes.carapi_client.find_tank_capacity")
    def test_forwards_matching_fields(self, find_tank_capacity):
        find_tank_capacity.return_value = {"capacity_l": 54.9}

        response = self.client.get(
            "/api/tank-size?year=2018&make=Toyota&model=Camry"
            "&cylinders=4&displ=2.5&city_mpg=29&highway_mpg=41"
            "&transmission=Automatic%20(S8)&base_model=Camry"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["capacity_l"], 54.9)
        find_tank_capacity.assert_called_once_with(
            "2018", "Toyota", "Camry", "4", "2.5", "29", "41", "Automatic (S8)", "Camry"
        )


class FuelPriceRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.client = create_app({
            "TESTING": True,
            "VEHICLE_DB_PATH": os.path.join(self.temp_dir.name, "vehicles.db"),
        }).test_client()

    @patch("server.routes.statcan_client.get_locations")
    def test_lists_statcan_locations(self, get_locations):
        get_locations.return_value = ["Canada", "Vancouver, British Columbia"]

        response = self.client.get("/api/fuel-price-locations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()[0], "Canada")

    def test_fuel_prices_requires_location(self):
        response = self.client.get("/api/fuel-prices")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "location is required")

    @patch("server.routes.statcan_client.get_latest_prices")
    def test_returns_latest_prices(self, get_latest_prices):
        get_latest_prices.return_value = {
            "location": "Vancouver, British Columbia",
            "period": "2026-07",
            "prices": {"regular": 2.007, "midgrade": None, "premium": 2.267, "diesel": 2.354},
        }

        response = self.client.get(
            "/api/fuel-prices?location=Vancouver%2C%20British%20Columbia"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["prices"]["regular"], 2.007)
        get_latest_prices.assert_called_once_with("Vancouver, British Columbia")


if __name__ == "__main__":
    unittest.main()
