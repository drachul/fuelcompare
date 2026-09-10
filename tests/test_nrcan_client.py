import csv
import io
import unittest
from unittest.mock import Mock, patch

import requests

from server import nrcan_client


FIELDS = [
    "Model year",
    "Make",
    "Model",
    "Vehicle class",
    "Engine size (L)",
    "Cylinders",
    "Transmission",
    "Fuel type",
    "City (L/100 km)",
    "Highway (L/100 km)",
    "Combined (L/100 km)",
    "Combined (mpg)",
    "CO2 emissions (g/km)",
    "CO2 rating",
    "Smog rating",
]


class NrcanClientTests(unittest.TestCase):
    def setUp(self):
        nrcan_client._resource_urls = None
        nrcan_client._resource_urls_expires_at = 0
        nrcan_client._dataset_cache = {}

    @staticmethod
    def response(*, payload=None, content=b""):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        response.content = content
        return response

    @staticmethod
    def csv_bytes(rows):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode()

    @patch.object(nrcan_client._session, "get")
    def test_discovers_resources_and_loads_vehicle_ratings_once(self, get):
        dataset_url = "https://example.test/my2025-2026-ratings.csv"
        metadata = {
            "success": True,
            "result": {
                "resources": [
                    {
                        "name": "2025-2026 Fuel Consumption Ratings (updated)",
                        "format": "CSV",
                        "language": ["en"],
                        "url": dataset_url,
                    },
                    {
                        "name": "Battery-electric vehicles 2012-2026",
                        "format": "CSV",
                        "language": ["en"],
                        "url": "https://example.test/ev.csv",
                    },
                ]
            },
        }
        rows = [
            {
                "Model year": "2026",
                "Make": "Toyota",
                "Model": "Camry AWD",
                "Vehicle class": "Mid-size",
                "Engine size (L)": "2.5",
                "Cylinders": "4",
                "Transmission": "AS8",
                "Fuel type": "X",
                "City (L/100 km)": "9.1",
                "Highway (L/100 km)": "6.7",
            },
            {
                "Model year": "2025",
                "Make": "Example",
                "Model": "E85 Car",
                "Vehicle class": "Compact",
                "Engine size (L)": "2.0",
                "Cylinders": "4",
                "Transmission": "A6",
                "Fuel type": "E",
                "City (L/100 km)": "12.0",
                "Highway (L/100 km)": "9.0",
            },
        ]

        def request(url, **_kwargs):
            if url == nrcan_client.DATASET_API_URL:
                return self.response(payload=metadata)
            self.assertEqual(url, dataset_url)
            return self.response(content=self.csv_bytes(rows))

        get.side_effect = request

        self.assertEqual(nrcan_client.get_years(), ["2026", "2025"])
        self.assertEqual(nrcan_client.get_makes("2026"), ["Toyota"])
        self.assertEqual(nrcan_client.get_models("2026", "toyota"), ["Camry AWD"])
        trims = nrcan_client.get_trims("2026", "Toyota", "camry awd")
        vehicle = nrcan_client.get_vehicle(trims[0]["value"])

        self.assertIn("2.5 L · 4 cyl · AS8 · Regular gasoline — NRCan", trims[0]["text"])
        self.assertTrue(vehicle["id"].startswith("nrcan:2026:"))
        self.assertEqual(vehicle["fuel_type"], "regular")
        self.assertEqual(vehicle["city_l_100km"], 9.1)
        self.assertAlmostEqual(vehicle["city_mpg"], 25.848, places=3)
        self.assertEqual(get.call_count, 2)

    @patch.object(nrcan_client._session, "get")
    def test_metadata_network_failure_has_clear_error(self, get):
        get.side_effect = requests.Timeout("timed out")

        with self.assertRaisesRegex(nrcan_client.NrcanDataError, "NRCan"):
            nrcan_client.get_years()


if __name__ == "__main__":
    unittest.main()
