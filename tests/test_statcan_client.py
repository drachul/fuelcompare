import csv
import io
import unittest
import zipfile
from unittest.mock import Mock, patch

import requests

from server import statcan_client


class StatsCanClientTests(unittest.TestCase):
    def setUp(self):
        statcan_client._cached_dataset = None
        statcan_client._cache_expires_at = 0

    @staticmethod
    def archive(rows):
        output = io.StringIO()
        writer = csv.DictWriter(
            output, fieldnames=["REF_DATE", "GEO", "Type of fuel", "UOM", "VALUE"]
        )
        writer.writeheader()
        writer.writerows(rows)
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("18100001.csv", output.getvalue())
            archive.writestr("18100001_MetaData.csv", "metadata")
        return archive_bytes.getvalue()

    @staticmethod
    def response(content):
        response = Mock()
        response.raise_for_status.return_value = None
        response.content = content
        return response

    @patch.object(statcan_client._session, "get")
    def test_returns_latest_prices_in_dollars_per_litre(self, get):
        rows = [
            {
                "REF_DATE": "2026-06",
                "GEO": "Vancouver, British Columbia",
                "Type of fuel": "Regular unleaded gasoline at self service filling stations",
                "UOM": "Cents per litre",
                "VALUE": "220.6",
            },
            {
                "REF_DATE": "2026-07",
                "GEO": "Vancouver, British Columbia",
                "Type of fuel": "Regular unleaded gasoline at self service filling stations",
                "UOM": "Cents per litre",
                "VALUE": "200.7",
            },
            {
                "REF_DATE": "2026-07",
                "GEO": "Vancouver, British Columbia",
                "Type of fuel": "Premium unleaded gasoline at self service filling stations",
                "UOM": "Cents per litre",
                "VALUE": "226.7",
            },
            {
                "REF_DATE": "2026-07",
                "GEO": "Vancouver, British Columbia",
                "Type of fuel": "Diesel fuel at self service filling stations",
                "UOM": "Cents per litre",
                "VALUE": "235.4",
            },
            {
                "REF_DATE": "2026-07",
                "GEO": "Vancouver, British Columbia",
                "Type of fuel": "Household heating fuel",
                "UOM": "Cents per litre",
                "VALUE": "203.4",
            },
        ]
        get.return_value = self.response(self.archive(rows))

        result = statcan_client.get_latest_prices("Vancouver, British Columbia")

        self.assertEqual(result["period"], "2026-07")
        self.assertEqual(result["prices"]["regular"], 2.007)
        self.assertEqual(result["prices"]["premium"], 2.267)
        self.assertEqual(result["prices"]["diesel"], 2.354)
        self.assertIsNone(result["prices"]["midgrade"])
        self.assertEqual(result["price_unit"], "liter")

    @patch.object(statcan_client._session, "get")
    def test_locations_use_cache_and_put_canada_first(self, get):
        rows = []
        for location in ("Vancouver, British Columbia", "Canada"):
            rows.append(
                {
                    "REF_DATE": "2026-07",
                    "GEO": location,
                    "Type of fuel": "Regular unleaded gasoline at self service filling stations",
                    "UOM": "Cents per litre",
                    "VALUE": "200.0",
                }
            )
        get.return_value = self.response(self.archive(rows))

        first = statcan_client.get_locations()
        second = statcan_client.get_locations()

        self.assertEqual(first, ["Canada", "Vancouver, British Columbia"])
        self.assertEqual(second, first)
        get.assert_called_once()

    @patch.object(statcan_client._session, "get")
    def test_network_failure_has_clear_error(self, get):
        get.side_effect = requests.Timeout("timed out")

        with self.assertRaisesRegex(statcan_client.StatsCanApiError, "Statistics Canada"):
            statcan_client.get_locations()

    @patch.object(statcan_client._session, "get")
    def test_rejects_unknown_location(self, get):
        rows = [
            {
                "REF_DATE": "2026-07",
                "GEO": "Canada",
                "Type of fuel": "Regular unleaded gasoline at self service filling stations",
                "UOM": "Cents per litre",
                "VALUE": "180.0",
            }
        ]
        get.return_value = self.response(self.archive(rows))

        with self.assertRaises(statcan_client.UnknownLocationError):
            statcan_client.get_latest_prices("Not a real place")


if __name__ == "__main__":
    unittest.main()
