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


if __name__ == "__main__":
    unittest.main()
