"""Latest Canadian fuel-price averages from Statistics Canada table 18-10-0001-01."""
from __future__ import annotations

import csv
import io
import threading
import time
import zipfile

import requests

DOWNLOAD_URL = "https://www150.statcan.gc.ca/n1/en/tbl/csv/18100001-eng.zip"
SOURCE_URL = "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000101"
REQUEST_TIMEOUT = 15
CACHE_TTL_SECONDS = 24 * 60 * 60
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
MAX_CSV_BYTES = 25 * 1024 * 1024

FUEL_TYPE_MAP = {
    "Regular unleaded gasoline at self service filling stations": "regular",
    "Premium unleaded gasoline at self service filling stations": "premium",
    "Diesel fuel at self service filling stations": "diesel",
}


class StatsCanApiError(RuntimeError):
    """Raised when the Statistics Canada dataset cannot be downloaded or parsed."""


class UnknownLocationError(ValueError):
    """Raised when a requested location is not present in the current dataset."""


_session = requests.Session()
_cache_lock = threading.Lock()
_cached_dataset: dict | None = None
_cache_expires_at = 0.0


def _download_dataset() -> dict:
    try:
        response = _session.get(DOWNLOAD_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        archive_bytes = response.content
    except requests.RequestException as exc:
        raise StatsCanApiError(f"Could not reach Statistics Canada: {exc}") from exc

    if not archive_bytes or len(archive_bytes) > MAX_DOWNLOAD_BYTES:
        raise StatsCanApiError("Statistics Canada returned an unexpected download size.")

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            data_files = [
                info
                for info in archive.infolist()
                if info.filename.endswith(".csv") and "metadata" not in info.filename.lower()
            ]
            if len(data_files) != 1 or data_files[0].file_size > MAX_CSV_BYTES:
                raise StatsCanApiError("Statistics Canada returned an unexpected archive.")

            with archive.open(data_files[0]) as raw_csv:
                rows = csv.DictReader(io.TextIOWrapper(raw_csv, encoding="utf-8-sig"))
                latest_period = ""
                location_prices: dict[str, dict[str, float]] = {}

                for row in rows:
                    fuel_key = FUEL_TYPE_MAP.get(row.get("Type of fuel", ""))
                    if not fuel_key or row.get("UOM") != "Cents per litre":
                        continue
                    period = row.get("REF_DATE", "")
                    if period < latest_period:
                        continue
                    if period > latest_period:
                        latest_period = period
                        location_prices = {}

                    value = row.get("VALUE", "")
                    location = row.get("GEO", "").strip()
                    if not value or not location:
                        continue
                    try:
                        dollars_per_litre = round(float(value) / 100, 3)
                    except ValueError:
                        continue
                    location_prices.setdefault(location, {})[fuel_key] = dollars_per_litre
    except (csv.Error, KeyError, UnicodeError, zipfile.BadZipFile) as exc:
        raise StatsCanApiError(f"Could not parse Statistics Canada data: {exc}") from exc

    if not latest_period or not location_prices:
        raise StatsCanApiError("Statistics Canada returned no current fuel prices.")

    return {"period": latest_period, "locations": location_prices}


def _get_dataset() -> dict:
    global _cached_dataset, _cache_expires_at

    now = time.monotonic()
    if _cached_dataset is not None and _cache_expires_at > now:
        return _cached_dataset

    with _cache_lock:
        now = time.monotonic()
        if _cached_dataset is not None and _cache_expires_at > now:
            return _cached_dataset
        dataset = _download_dataset()
        _cached_dataset = dataset
        _cache_expires_at = now + CACHE_TTL_SECONDS
        return dataset


def get_locations() -> list[str]:
    locations = _get_dataset()["locations"]
    return sorted(locations, key=lambda location: (location != "Canada", location))


def get_latest_prices(location: str) -> dict:
    dataset = _get_dataset()
    prices = dataset["locations"].get(location)
    if prices is None:
        raise UnknownLocationError(f"Unknown Statistics Canada location: {location}")

    return {
        "location": location,
        "period": dataset["period"],
        "currency": "CAD",
        "price_unit": "liter",
        "prices": {
            "regular": prices.get("regular"),
            "midgrade": None,
            "premium": prices.get("premium"),
            "diesel": prices.get("diesel"),
        },
        "source": "Statistics Canada table 18-10-0001-01",
        "source_url": SOURCE_URL,
    }
