"""Fuel cost comparison math, ported from the original spreadsheet.

Formulas (per vehicle):
    overall_l_100km = city_l_100km * city_weight + highway_l_100km * highway_weight
    range_km        = tank_size_l / overall_l_100km * 100
    cost_per_tank   = tank_size_l * price_per_liter[fuel_type]
    fillups_per_year = annual_km / range_km
    annual_cost     = fillups_per_year * cost_per_tank
"""
from __future__ import annotations

KM_PER_MILE = 1.60934
LITERS_PER_GALLON = 3.785411784

FUEL_TYPES = ("regular", "midgrade", "premium", "diesel")


class CalcError(ValueError):
    pass


def _to_annual_km(distance: dict) -> float:
    value = float(distance.get("value", 0) or 0)
    unit = distance.get("unit", "km")
    period = distance.get("period", "year")
    if value <= 0:
        raise CalcError("Distance must be greater than zero.")
    km = value * KM_PER_MILE if unit == "mi" else value
    return km * 12 if period == "month" else km


def _normalized_weights(weighting: dict) -> tuple[float, float]:
    city = float(weighting.get("city", 50) or 0)
    highway = float(weighting.get("highway", 50) or 0)
    total = city + highway
    if total <= 0:
        raise CalcError("City/highway weighting must add up to more than zero.")
    return city / total, highway / total


def _prices_per_liter(prices: dict, unit: str) -> dict:
    per_liter = {}
    for fuel in FUEL_TYPES:
        price = float(prices.get(fuel, 0) or 0)
        per_liter[fuel] = price / LITERS_PER_GALLON if unit == "gallon" else price
    return per_liter


def _tank_liters(vehicle: dict) -> float:
    size = float(vehicle.get("tank_size", 0) or 0)
    if size <= 0:
        raise CalcError(f"{vehicle.get('label') or 'A vehicle'} needs a tank size greater than zero.")
    return size * LITERS_PER_GALLON if vehicle.get("tank_unit") == "gallon" else size


def compute_comparison(payload: dict) -> dict:
    annual_km = _to_annual_km(payload.get("distance", {}))
    city_w, highway_w = _normalized_weights(payload.get("weighting", {}))
    price_unit = payload.get("price_unit", "liter")
    prices = _prices_per_liter(payload.get("prices", {}), price_unit)

    vehicles = payload.get("vehicles") or []
    if len(vehicles) < 1:
        raise CalcError("Add at least one vehicle to compare.")

    results = []
    for idx, vehicle in enumerate(vehicles):
        label = vehicle.get("label") or f"Vehicle {idx + 1}"
        fuel_type = vehicle.get("fuel_type")
        if fuel_type not in FUEL_TYPES:
            raise CalcError(f"{label}: unsupported fuel type.")

        city = float(vehicle.get("city_l_100km", 0) or 0)
        highway = float(vehicle.get("highway_l_100km", 0) or 0)
        if city <= 0 or highway <= 0:
            raise CalcError(f"{label}: city/highway consumption must be greater than zero.")

        tank_l = _tank_liters(vehicle)
        overall_l_100km = city * city_w + highway * highway_w
        range_km = tank_l / overall_l_100km * 100
        cost_per_tank = tank_l * prices[fuel_type]
        fillups_per_year = annual_km / range_km
        annual_cost = fillups_per_year * cost_per_tank

        results.append({
            "label": label,
            "fuel_type": fuel_type,
            "overall_l_100km": round(overall_l_100km, 3),
            "range_km": round(range_km, 1),
            "cost_per_tank": round(cost_per_tank, 2),
            "fillups_per_year": round(fillups_per_year, 2),
            "annual_cost": round(annual_cost, 2),
        })

    cheapest = min(results, key=lambda r: r["annual_cost"])
    for r in results:
        r["delta_vs_cheapest"] = round(r["annual_cost"] - cheapest["annual_cost"], 2)

    return {
        "annual_km": round(annual_km, 1),
        "city_weight": round(city_w * 100, 1),
        "highway_weight": round(highway_w * 100, 1),
        "vehicles": results,
        "cheapest_label": cheapest["label"],
    }
