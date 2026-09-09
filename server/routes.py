import sqlite3

from flask import Blueprint, current_app, jsonify, request

from . import carapi_client, epa_client, statcan_client, vehicle_store
from .calc import LITERS_PER_GALLON, CalcError, compute_comparison

bp = Blueprint("api", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/years")
def years():
    try:
        return jsonify(epa_client.get_years())
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/makes")
def makes():
    year = request.args.get("year", "")
    if not year:
        return jsonify({"error": "year is required"}), 400
    try:
        return jsonify(epa_client.get_makes(year))
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/models")
def models():
    year = request.args.get("year", "")
    make = request.args.get("make", "")
    if not year or not make:
        return jsonify({"error": "year and make are required"}), 400
    try:
        return jsonify(epa_client.get_models(year, make))
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/trims")
def trims():
    year = request.args.get("year", "")
    make = request.args.get("make", "")
    model = request.args.get("model", "")
    if not year or not make or not model:
        return jsonify({"error": "year, make and model are required"}), 400
    try:
        return jsonify(epa_client.get_trims(year, make, model))
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/vehicle/<vehicle_id>")
def vehicle(vehicle_id):
    cached = vehicle_store.get_by_epa_id(vehicle_id)
    required_fields = ("year", "make", "model", "city_l_100km", "highway_l_100km")
    if cached is not None and all(cached.get(field) for field in required_fields):
        cached["cached"] = True
        return jsonify(cached)
    try:
        result = epa_client.get_vehicle(vehicle_id)
        saved = vehicle_store.save_vehicle(result, "EPA")
        saved["cached"] = False
        return jsonify(saved)
    except epa_client.EpaApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/saved-vehicles")
def saved_vehicles():
    vehicles = vehicle_store.list_vehicles()
    return jsonify(
        [
            {
                "record_id": vehicle["record_id"],
                "label": vehicle["label"],
                "year": vehicle.get("year", ""),
                "make": vehicle.get("make", ""),
                "model": vehicle.get("model", ""),
                "trim": vehicle.get("trim", ""),
                "saved_at": vehicle["saved_at"],
            }
            for vehicle in vehicles
        ]
    )


@bp.get("/saved-vehicle/<int:record_id>")
def saved_vehicle(record_id):
    result = vehicle_store.get_by_id(record_id)
    if result is None:
        return jsonify({"error": "Saved vehicle not found"}), 404
    result["cached"] = True
    return jsonify(result)


@bp.get("/fuel-price-locations")
def fuel_price_locations():
    try:
        return jsonify(statcan_client.get_locations())
    except statcan_client.StatsCanApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/fuel-prices")
def fuel_prices():
    location = request.args.get("location", "").strip()
    if not location:
        return jsonify({"error": "location is required"}), 400
    try:
        return jsonify(statcan_client.get_latest_prices(location))
    except statcan_client.UnknownLocationError as exc:
        return jsonify({"error": str(exc)}), 404
    except statcan_client.StatsCanApiError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/tank-size")
def tank_size():
    year = request.args.get("year", "")
    make = request.args.get("make", "")
    model = request.args.get("model", "")
    cylinders = request.args.get("cylinders", "")
    displ = request.args.get("displ", "")
    city_mpg = request.args.get("city_mpg", "")
    highway_mpg = request.args.get("highway_mpg", "")
    transmission = request.args.get("transmission", "")
    base_model = request.args.get("base_model", "")
    vehicle_id = request.args.get("vehicle_id", "").strip()
    if not year or not make or not model:
        return jsonify({"error": "year, make and model are required"}), 400

    cached = vehicle_store.get_by_epa_id(vehicle_id) if vehicle_id else None
    if cached and cached.get("tank_size"):
        capacity_l = float(cached["tank_size"])
        if cached.get("tank_unit") == "gallon":
            capacity_l *= LITERS_PER_GALLON
        return jsonify(
            {
                "capacity_l": round(capacity_l, 1),
                "matched_trim": cached.get("tank_matched_trim", ""),
                "matches": [],
                "ambiguous": False,
                "source": "SQLite vehicle cache",
                "cached": True,
            }
        )
    if cached and cached.get("tank_lookup") is not None:
        result = dict(cached["tank_lookup"])
        result["cached"] = True
        result["source"] = "SQLite vehicle cache"
        return jsonify(result)

    result = carapi_client.find_tank_capacity(
        year,
        make,
        model,
        cylinders,
        displ,
        city_mpg,
        highway_mpg,
        transmission,
        base_model,
    )
    if result is not None and vehicle_id:
        cached_fields = {
            "epa_vehicle_id": vehicle_id,
            "tank_lookup": result,
        }
        if result.get("capacity_l"):
            cached_fields.update(
                {
                    "tank_size": result["capacity_l"],
                    "tank_unit": "liter",
                    "tank_matched_trim": result.get("matched_trim", ""),
                }
            )
        vehicle_store.save_vehicle(cached_fields, "CarAPI")
    return jsonify(result)


@bp.post("/compare")
def compare():
    payload = request.get_json(silent=True) or {}
    try:
        result = compute_comparison(payload)
    except CalcError as exc:
        return jsonify({"error": str(exc)}), 400

    # A successful comparison guarantees the values are usable. Persist the
    # submitted fields, including any manual corrections, for future reuse.
    allowed_fields = {
        "epa_vehicle_id",
        "label",
        "year",
        "make",
        "model",
        "trim",
        "city_l_100km",
        "highway_l_100km",
        "fuel_type",
        "tank_size",
        "tank_unit",
    }
    for submitted in payload.get("vehicles") or []:
        vehicle_data = {
            key: value for key, value in submitted.items() if key in allowed_fields
        }
        try:
            vehicle_store.save_vehicle(
                vehicle_data,
                "manual" if not vehicle_data.get("epa_vehicle_id") else "EPA + manual",
                submitted.get("record_id"),
            )
        except sqlite3.Error:
            current_app.logger.exception("Could not cache submitted vehicle")
    return jsonify(result)
