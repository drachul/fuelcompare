"""Best-effort fuel-tank lookup using CarAPI.

FuelEconomy.gov does not publish tank capacity. CarAPI's mileage records do,
but its trim hierarchy does not map directly to EPA vehicle IDs. We therefore
rank same-year/make/model records using the engine and MPG values that the two
datasets have in common. A result is auto-selected only when that ranking
clearly identifies one capacity; otherwise the possible matches are returned
for the user to choose from.

Unauthenticated CarAPI requests use its public 2015-2020 demo dataset. Set
CARAPI_API_TOKEN and CARAPI_API_SECRET to use a subscribed full dataset.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import threading
import time

import requests

BASE_URL = "https://carapi.app/api"
REQUEST_TIMEOUT = 8
CACHE_TTL_SECONDS = 24 * 60 * 60
ERROR_CACHE_TTL_SECONDS = 5 * 60
LITERS_PER_GALLON = 3.785411784

_CYLINDERS_RE = re.compile(r"\b(\d+)\s*cyl\b", re.IGNORECASE)
_DISPLACEMENT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*l\b", re.IGNORECASE)
_MODEL_SUFFIX_RE = re.compile(
    r"\s+(?:2wd|4wd|awd|fwd|rwd|4matic|quattro|xdrive)\b.*$", re.IGNORECASE
)


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
_auth_lock = threading.Lock()
_jwt = ""
_jwt_expires_at = 0.0
_auth_retry_after = 0.0


def _normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _as_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _jwt_expiration(token: str) -> float:
    """Read a JWT expiry without verifying it; CarAPI still verifies the token."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        return float(decoded["exp"])
    except (binascii.Error, IndexError, KeyError, TypeError, UnicodeError, ValueError):
        return time.time() + ERROR_CACHE_TTL_SECONDS


def _get_jwt() -> str:
    global _jwt, _jwt_expires_at, _auth_retry_after

    api_token = os.environ.get("CARAPI_API_TOKEN", "").strip()
    api_secret = os.environ.get("CARAPI_API_SECRET", "").strip()
    if not api_token or not api_secret:
        return ""

    now = time.time()
    if _jwt and _jwt_expires_at > now + 60:
        return _jwt
    if _auth_retry_after > now:
        return ""

    with _auth_lock:
        now = time.time()
        if _jwt and _jwt_expires_at > now + 60:
            return _jwt
        try:
            response = _session.post(
                f"{BASE_URL}/auth/login",
                json={"api_token": api_token, "api_secret": api_secret},
                headers={"Accept": "text/plain"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            token = response.text.strip()
            # Some HTTP clients expose a JSON string including its quotes.
            if token.startswith('"'):
                token = json.loads(token)
            if not isinstance(token, str) or token.count(".") != 2:
                raise ValueError("CarAPI returned an invalid token")
        except (requests.RequestException, ValueError):
            _auth_retry_after = now + ERROR_CACHE_TTL_SECONDS
            return ""

        _jwt = token
        _jwt_expires_at = _jwt_expiration(token)
        _auth_retry_after = 0.0
        return _jwt


def _request_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    token = _get_jwt()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_mileages(year: str, make: str, model: str) -> list[dict]:
    cache_key = f"{year}|{_normalized(make)}|{_normalized(model)}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    params = {
        "year": year,
        "make": make,
        "model": model,
        "verbose": "yes",
        "limit": 100,
    }
    try:
        response = _session.get(
            f"{BASE_URL}/mileages/v2",
            params=params,
            headers=_request_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        rows = data.get("data") or []
        if not isinstance(rows, list):
            raise ValueError("CarAPI returned an invalid response")
    except (requests.RequestException, TypeError, ValueError):
        _cache.set(cache_key, [], ERROR_CACHE_TTL_SECONDS)
        return []

    # The API's make/model filters are fuzzy. Do exact punctuation-insensitive
    # filtering locally so similarly named vehicles cannot leak into a match.
    expected_year = str(year)
    make_key = _normalized(make)
    model_key = _normalized(model)
    rows = [
        row
        for row in rows
        if str(row.get("year", "")) == expected_year
        and _normalized(row.get("make")) == make_key
        and _normalized(row.get("model")) == model_key
    ]
    _cache.set(cache_key, rows)
    return rows


def _description(row: dict) -> str:
    return str(
        row.get("trim_description")
        or row.get("submodel")
        or row.get("trim")
        or "Unknown trim"
    )


def _transmission_kind(value: str) -> str:
    value = value.lower()
    if "cvt" in value:
        return "cvt"
    if "manual" in value or re.search(r"\b\d+m\b", value):
        return "manual"
    if "automatic" in value or re.search(r"\b\d+a\b", value):
        return "automatic"
    return ""


def _score(
    row: dict,
    cylinders: str,
    displacement_l: str,
    city_mpg: str,
    highway_mpg: str,
    transmission: str,
) -> tuple[float, int]:
    """Return (lower-is-better score, number of comparable signals)."""
    description = _description(row)
    score = 0.0
    signals = 0

    wanted_cylinders = _as_float(cylinders)
    cylinder_match = _CYLINDERS_RE.search(description)
    if wanted_cylinders is not None and cylinder_match:
        signals += 1
        score += abs(wanted_cylinders - float(cylinder_match.group(1))) * 25

    wanted_displacement = _as_float(displacement_l)
    displacement_match = _DISPLACEMENT_RE.search(description)
    if wanted_displacement is not None and displacement_match:
        signals += 1
        score += abs(wanted_displacement - float(displacement_match.group(1))) * 10

    for wanted, actual, weight in (
        (_as_float(city_mpg), _as_float(row.get("epa_city_mpg")), 2.0),
        (_as_float(highway_mpg), _as_float(row.get("epa_highway_mpg")), 1.0),
    ):
        if wanted is not None and actual is not None:
            signals += 1
            score += abs(wanted - actual) * weight

    wanted_transmission = _transmission_kind(transmission)
    actual_transmission = _transmission_kind(description)
    if wanted_transmission and actual_transmission:
        signals += 1
        if wanted_transmission != actual_transmission:
            score += 10

    return score, signals


def _model_candidates(model: str, base_model: str) -> list[str]:
    candidates = [base_model, model, _MODEL_SUFFIX_RE.sub("", model).strip()]
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def find_tank_capacity(
    year: str,
    make: str,
    model: str,
    cylinders: str = "",
    displacement_l: str = "",
    city_mpg: str = "",
    highway_mpg: str = "",
    transmission: str = "",
    base_model: str = "",
) -> dict | None:
    rows: list[dict] = []
    for candidate_model in _model_candidates(model, base_model):
        rows = _get_mileages(year, make, candidate_model)
        if rows:
            break

    ranked = []
    for row in rows:
        gallons = _as_float(row.get("fuel_tank_capacity"))
        if gallons is None or gallons <= 0:
            continue
        score, signals = _score(
            row, cylinders, displacement_l, city_mpg, highway_mpg, transmission
        )
        ranked.append(
            {
                "capacity_l": round(gallons * LITERS_PER_GALLON, 1),
                "matched_trim": _description(row),
                "score": score,
                "signals": signals,
            }
        )

    if not ranked:
        return None

    ranked.sort(key=lambda match: (match["score"], match["matched_trim"]))
    best = ranked[0]

    # Keep useful alternatives, while collapsing duplicate trim/capacity rows.
    matches = []
    seen = set()
    for match in ranked:
        # Very different engines/MPG variants are not useful suggestions even
        # though they share the same marketed model name.
        if match["score"] > best["score"] + 10:
            continue
        key = (match["capacity_l"], match["matched_trim"])
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            {
                "capacity_l": match["capacity_l"],
                "matched_trim": match["matched_trim"],
            }
        )
        if len(matches) == 8:
            break

    capacities = {match["capacity_l"] for match in ranked}
    next_other_capacity = next(
        (match for match in ranked[1:] if match["capacity_l"] != best["capacity_l"]),
        None,
    )
    clearly_ranked = (
        best["signals"] > 0
        and next_other_capacity is not None
        and next_other_capacity["score"] - best["score"] >= 2
    )
    confident = len(capacities) == 1 or clearly_ranked

    return {
        "capacity_l": best["capacity_l"] if confident else None,
        "matched_trim": best["matched_trim"] if confident else "",
        "matches": matches,
        "ambiguous": not confident,
        "source": "CarAPI",
    }
