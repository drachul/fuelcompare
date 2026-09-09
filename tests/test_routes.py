import unittest
from unittest.mock import patch

from server import create_app


class TankSizeRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

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
        self.client = create_app().test_client()

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
