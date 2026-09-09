"""Client for the US DOE/EPA fueleconomy.gov public data API (no key required).

API docs: https://www.fueleconomy.gov/feg/ws/index.shtml
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import requests

BASE_URL = "https://www.fueleconomy.gov/ws/rest/vehicle"
REQUEST_TIMEOUT = 8
CACHE_TTL_SECONDS = 24 * 60 * 60

# fueleconomy.gov's fuelType1 values, mapped onto the four fuel categories
# used by the original spreadsheet. Anything not listed (Electricity, E85,
# CNG, Hydrogen, ...) is reported back as "unsupported".
FUEL_TYPE_MAP = {
    "Regular Gasoline": "regular",
    "Midgrade Gasoline": "midgrade",
    "Premium Gasoline": "premium",
    "Diesel": "diesel",
}

MPG_TO_L_PER_100KM = 235.214583


class EpaApiError(RuntimeError):
    """Raised when the upstream fueleconomy.gov API can't be reached or parsed."""


class _TTLCache:
    def __init__(self):
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key, value, ttl=CACHE_TTL_SECONDS):
        self._store[key] = (time.monotonic() + ttl, value)


_cache = _TTLCache()
_session = requests.Session()


def _get_xml(path: str, params: dict) -> ET.Element:
    cache_key = f"{path}?{sorted(params.items())}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        resp = _session.get(f"{BASE_URL}{path}", params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except requests.RequestException as exc:
        raise EpaApiError(f"Could not reach fueleconomy.gov: {exc}") from exc
    except ET.ParseError as exc:
        raise EpaApiError(f"Unexpected response from fueleconomy.gov: {exc}") from exc
    _cache.set(cache_key, root)
    return root


def _menu_items(root: ET.Element) -> list[dict]:
    items = []
    for item in root.findall("menuItem"):
        text = item.findtext("text", default="")
        value = item.findtext("value", default="")
        items.append({"text": text, "value": value})
    return items


def get_years() -> list[str]:
    root = _get_xml("/menu/year", {})
    years = [i["value"] for i in _menu_items(root)]
    return sorted(years, reverse=True)


def get_makes(year: str) -> list[str]:
    root = _get_xml("/menu/make", {"year": year})
    return sorted(i["value"] for i in _menu_items(root))


def get_models(year: str, make: str) -> list[str]:
    root = _get_xml("/menu/model", {"year": year, "make": make})
    return sorted(i["value"] for i in _menu_items(root))


def get_trims(year: str, make: str, model: str) -> list[dict]:
    root = _get_xml("/menu/options", {"year": year, "make": make, "model": model})
    # value is the numeric vehicle id fueleconomy.gov uses for /vehicle/{id}
    return _menu_items(root)


def _float(el: ET.Element, tag: str, default=0.0) -> float:
    raw = el.findtext(tag)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def get_vehicle(vehicle_id: str) -> dict:
    cache_key = f"/{vehicle_id}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        resp = _session.get(f"{BASE_URL}/{vehicle_id}", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        v = ET.fromstring(resp.content)
    except requests.RequestException as exc:
        raise EpaApiError(f"Could not reach fueleconomy.gov: {exc}") from exc
    except ET.ParseError as exc:
        raise EpaApiError(f"Unexpected response from fueleconomy.gov: {exc}") from exc

    city_mpg = _float(v, "city08")
    highway_mpg = _float(v, "highway08")
    fuel_type1 = v.findtext("fuelType1", default="") or ""

    result = {
        "id": vehicle_id,
        "year": v.findtext("year", default=""),
        "make": v.findtext("make", default=""),
        "model": v.findtext("model", default=""),
        "base_model": v.findtext("baseModel", default=""),
        "trany": v.findtext("trany", default=""),
        "drive": v.findtext("drive", default=""),
        "vclass": v.findtext("VClass", default=""),
        "cylinders": v.findtext("cylinders", default=""),
        "displ": v.findtext("displ", default=""),
        "fuel_type_label": fuel_type1,
        "fuel_type": FUEL_TYPE_MAP.get(fuel_type1, "unsupported"),
        "city_mpg": city_mpg,
        "highway_mpg": highway_mpg,
        "city_l_100km": round(MPG_TO_L_PER_100KM / city_mpg, 3) if city_mpg else None,
        "highway_l_100km": round(MPG_TO_L_PER_100KM / highway_mpg, 3) if highway_mpg else None,
    }
    _cache.set(cache_key, result)
    return result
