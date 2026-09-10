"""Client for Natural Resources Canada's fuel-consumption ratings datasets.

The public search tool is backed by downloadable CSV resources published on
Canada's Open Government Portal. Resource URLs are discovered from the dataset
metadata so new model-year files can be picked up without an application
release.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import time

import requests


DATASET_ID = "98f1a129-f628-4ce4-b24d-6f16bf24dd64"
DATASET_API_URL = "https://open.canada.ca/data/api/3/action/package_show"
SEARCH_URL = "https://fcr-ccc.nrcan-rncan.gc.ca/en/Search"
REQUEST_TIMEOUT = 12
CACHE_TTL_SECONDS = 24 * 60 * 60
MPG_TO_L_PER_100KM = 235.214583

RESOURCE_NAME_RE = re.compile(
    r"^(?P<start>\d{4})(?:-(?P<end>\d{4}))? Fuel Consumption Ratings",
    re.IGNORECASE,
)

FUEL_TYPE_MAP = {
    "X": ("Regular gasoline", "regular"),
    "Z": ("Premium gasoline", "premium"),
    "D": ("Diesel", "diesel"),
    "E": ("Ethanol (E85)", "unsupported"),
    "N": ("Natural gas", "unsupported"),
}


class NrcanDataError(RuntimeError):
    """Raised when the NRCan dataset cannot be reached or parsed."""


_session = requests.Session()
_resource_urls: dict[str, str] | None = None
_resource_urls_expires_at = 0.0
_dataset_cache: dict[str, tuple[float, list[dict]]] = {}


def _float(row: dict, field: str) -> float | None:
    try:
        return float(row.get(field) or "")
    except (TypeError, ValueError):
        return None


def _vehicle_id(row: dict) -> str:
    identity = "\x1f".join(
        str(row.get(field) or "").strip()
        for field in (
            "Model year",
            "Make",
            "Model",
            "Engine size (L)",
            "Cylinders",
            "Transmission",
            "Fuel type",
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    year = str(row.get("Model year") or "").strip()
    return f"nrcan:{year}:{digest}"


def _resource_map() -> dict[str, str]:
    global _resource_urls, _resource_urls_expires_at

    now = time.monotonic()
    if _resource_urls is not None and now < _resource_urls_expires_at:
        return _resource_urls

    try:
        response = _session.get(
            DATASET_API_URL,
            params={"id": DATASET_ID},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise ValueError("dataset metadata reported a failure")

        urls: dict[str, str] = {}
        for resource in payload.get("result", {}).get("resources", []):
            if str(resource.get("format") or "").upper() != "CSV":
                continue
            languages = resource.get("language") or []
            if "en" not in languages:
                continue
            match = RESOURCE_NAME_RE.match(str(resource.get("name") or ""))
            url = str(resource.get("url") or "")
            if not match or not url:
                continue
            start = int(match.group("start"))
            end = int(match.group("end") or start)
            for year in range(start, end + 1):
                urls[str(year)] = url
        if not urls:
            raise ValueError("no English conventional-vehicle CSV resources found")
    except (requests.RequestException, ValueError, TypeError) as exc:
        if _resource_urls is not None:
            return _resource_urls
        raise NrcanDataError(f"Could not load NRCan vehicle dataset metadata: {exc}") from exc

    _resource_urls = urls
    _resource_urls_expires_at = now + CACHE_TTL_SECONDS
    return urls


def _parse_records(content: bytes) -> list[dict]:
    try:
        text = content.decode("utf-8-sig")
        rows = csv.DictReader(io.StringIO(text))
        required = {
            "Model year",
            "Make",
            "Model",
            "Engine size (L)",
            "Cylinders",
            "Transmission",
            "Fuel type",
            "City (L/100 km)",
            "Highway (L/100 km)",
        }
        if not rows.fieldnames or not required.issubset(rows.fieldnames):
            raise ValueError("CSV columns did not match the published schema")

        records = []
        for row in rows:
            city = _float(row, "City (L/100 km)")
            highway = _float(row, "Highway (L/100 km)")
            year = str(row.get("Model year") or "").strip()
            make = str(row.get("Make") or "").strip()
            model = str(row.get("Model") or "").strip()
            if not year or not make or not model or not city or not highway:
                continue

            fuel_code = str(row.get("Fuel type") or "").strip().upper()
            fuel_label, fuel_type = FUEL_TYPE_MAP.get(
                fuel_code,
                (fuel_code or "Unknown", "unsupported"),
            )
            engine = str(row.get("Engine size (L)") or "").strip()
            cylinders = str(row.get("Cylinders") or "").strip()
            transmission = str(row.get("Transmission") or "").strip()
            vehicle_id = _vehicle_id(row)
            trim_parts = [
                f"{engine} L" if engine else "",
                f"{cylinders} cyl" if cylinders else "",
                transmission,
                fuel_label,
            ]
            records.append(
                {
                    "id": vehicle_id,
                    "year": year,
                    "make": make,
                    "model": model,
                    "base_model": model,
                    "trim": " · ".join(part for part in trim_parts if part),
                    "trany": transmission,
                    "drive": "",
                    "vclass": str(row.get("Vehicle class") or "").strip(),
                    "cylinders": cylinders,
                    "displ": engine,
                    "fuel_type_label": fuel_label,
                    "fuel_type": fuel_type,
                    "city_mpg": round(MPG_TO_L_PER_100KM / city, 3),
                    "highway_mpg": round(MPG_TO_L_PER_100KM / highway, 3),
                    "city_l_100km": city,
                    "highway_l_100km": highway,
                    "source_url": SEARCH_URL,
                }
            )
        if not records:
            raise ValueError("CSV contained no usable conventional vehicles")
        return records
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise NrcanDataError(f"Could not parse NRCan vehicle ratings: {exc}") from exc


def _records_for_year(year: str) -> list[dict]:
    resource_url = _resource_map().get(str(year))
    if not resource_url:
        return []

    now = time.monotonic()
    cached = _dataset_cache.get(resource_url)
    if cached and now < cached[0]:
        return cached[1]

    try:
        response = _session.get(resource_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        records = _parse_records(response.content)
    except requests.RequestException as exc:
        if cached:
            return cached[1]
        raise NrcanDataError(f"Could not download NRCan vehicle ratings: {exc}") from exc

    _dataset_cache[resource_url] = (now + CACHE_TTL_SECONDS, records)
    return records


def get_years() -> list[str]:
    return sorted(_resource_map(), key=int, reverse=True)


def get_makes(year: str) -> list[str]:
    return sorted(
        {record["make"] for record in _records_for_year(year) if record["year"] == str(year)},
        key=str.casefold,
    )


def get_models(year: str, make: str) -> list[str]:
    make_key = make.casefold()
    return sorted(
        {
            record["model"]
            for record in _records_for_year(year)
            if record["year"] == str(year) and record["make"].casefold() == make_key
        },
        key=str.casefold,
    )


def get_trims(year: str, make: str, model: str) -> list[dict]:
    make_key = make.casefold()
    model_key = model.casefold()
    matches = [
        record
        for record in _records_for_year(year)
        if record["year"] == str(year)
        and record["make"].casefold() == make_key
        and record["model"].casefold() == model_key
    ]
    return [
        {"text": f'{record["trim"]} — NRCan', "value": record["id"]}
        for record in sorted(matches, key=lambda record: record["trim"].casefold())
    ]


def get_vehicle(vehicle_id: str) -> dict:
    parts = vehicle_id.split(":", 2)
    if len(parts) != 3 or parts[0] != "nrcan" or not parts[1].isdigit():
        raise NrcanDataError("Invalid NRCan vehicle identifier")
    for record in _records_for_year(parts[1]):
        if record["id"] == vehicle_id:
            return record.copy()
    raise NrcanDataError("NRCan vehicle record was not found")
